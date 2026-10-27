using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace RobotFramework.UnityBridge
{
    // This file deliberately has no Unity API dependency. Network work stays off the main thread.
    internal sealed class RpcWork
    {
        internal readonly RpcRequest Request;
        internal readonly TaskCompletionSource<JObject> Completion =
            new TaskCompletionSource<JObject>(TaskCreationOptions.RunContinuationsAsynchronously);
        private int cancelled;
        internal bool Cancelled => Volatile.Read(ref cancelled) != 0;
        internal RpcWork(RpcRequest request) { Request = request; }
        internal void Cancel()
        {
            Interlocked.Exchange(ref cancelled, 1);
            Completion.TrySetCanceled();
        }
    }

    internal sealed class TcpServer : IDisposable
    {
        private readonly TcpListener listener;
        private readonly Func<RpcWork, bool> submit;
        private readonly string unityVersion;
        private readonly Action<string> diagnostic;
        private readonly object gate = new object();
        private readonly HashSet<Session> sessions = new HashSet<Session>();
        private Session active;
        private volatile bool stopped;

        internal TcpServer(int port, string unityVersion, Func<RpcWork, bool> submit, Action<string> diagnostic = null)
        {
            this.unityVersion = unityVersion;
            this.submit = submit;
            this.diagnostic = diagnostic;
            listener = new TcpListener(IPAddress.Loopback, port);
        }

        internal int Port => ((IPEndPoint)listener.LocalEndpoint).Port;

        internal void Start()
        {
            listener.Start(4);
            Task.Run((Action)AcceptLoop);
        }

        private void AcceptLoop()
        {
            while (!stopped)
            {
                TcpClient client;
                try { client = listener.AcceptTcpClient(); }
                catch (SocketException) { if (stopped) return; continue; }
                catch (ObjectDisposedException) { return; }
                Session session;
                lock (gate)
                {
                    if (stopped || sessions.Count >= 5) { client.Close(); continue; }
                    bool busy = active != null && !active.Closed;
                    session = new Session(client, busy, unityVersion, submit, OnClosed, diagnostic);
                    sessions.Add(session);
                    if (!busy) active = session;
                }
                Task.Run((Action)session.Run);
            }
        }

        private void OnClosed(Session session)
        {
            lock (gate)
            {
                sessions.Remove(session);
                if (ReferenceEquals(active, session)) active = null;
            }
        }

        public void Dispose()
        {
            stopped = true;
            listener.Stop();
            Session[] snapshot;
            lock (gate) { snapshot = new Session[sessions.Count]; sessions.CopyTo(snapshot); }
            foreach (var session in snapshot) session.Close();
        }

        private sealed class Session
        {
            private const int MaxFrame = 64 * 1024;
            private static readonly Encoding Utf8 = new UTF8Encoding(false, true);
            private readonly TcpClient client;
            private readonly bool rejectBusy;
            private readonly string unityVersion;
            private readonly Func<RpcWork, bool> submit;
            private readonly Action<Session> onClosed;
            private readonly Action<string> diagnostic;
            private readonly object writeGate = new object();
            private readonly string sessionId = Guid.NewGuid().ToString("N");
            private RpcWork inFlight;
            private int closed;
            private int lastId;
            private bool handshaken;
            internal bool Closed => Volatile.Read(ref closed) != 0;

            internal Session(TcpClient client, bool rejectBusy, string unityVersion,
                Func<RpcWork, bool> submit, Action<Session> onClosed, Action<string> diagnostic)
            {
                this.client = client;
                this.rejectBusy = rejectBusy;
                this.unityVersion = unityVersion;
                this.submit = submit;
                this.onClosed = onClosed;
                this.diagnostic = diagnostic;
                client.NoDelay = true;
            }

            internal void Run()
            {
                double acceptedAt = BridgeClock.Now;
                double frameStarted = 0;
                var frame = new List<byte>();
                var buffer = new byte[8192];
                try
                {
                    NetworkStream stream = client.GetStream();
                    stream.ReadTimeout = 200;
                    stream.WriteTimeout = 2000;
                    while (!Closed)
                    {
                        if ((!handshaken && BridgeClock.Now - acceptedAt >= 5)
                            || (frame.Count > 0 && BridgeClock.Now - frameStarted >= 5)) break;
                        int count;
                        try { count = stream.Read(buffer, 0, buffer.Length); }
                        catch (IOException error) when (IsReadTimeout(error)) { continue; }
                        if (count == 0) break;
                        if ((!handshaken && BridgeClock.Now - acceptedAt >= 5)
                            || (frame.Count > 0 && BridgeClock.Now - frameStarted >= 5)) break;
                        for (int i = 0; i < count && !Closed; i++)
                        {
                            byte value = buffer[i];
                            if (value == 10)
                            {
                                if (frame.Count > 0 && frame[frame.Count - 1] == 13) frame.RemoveAt(frame.Count - 1);
                                if (frame.Count > MaxFrame) throw new IOException("Frame exceeds 64 KiB");
                                string line = Utf8.GetString(frame.ToArray());
                                frame.Clear();
                                Handle(line, BridgeClock.Now);
                            }
                            else
                            {
                                if (frame.Count == 0) frameStarted = BridgeClock.Now;
                                frame.Add(value);
                                if (frame.Count > MaxFrame + (value == 13 ? 1 : 0))
                                    throw new IOException("Frame exceeds 64 KiB");
                            }
                        }
                    }
                }
                catch (Exception error) when (error is IOException || error is SocketException
                    || error is ObjectDisposedException || error is DecoderFallbackException || error is JsonException)
                { diagnostic?.Invoke("Closing unusable stream: " + error.Message); }
                finally { Close(); }
            }

            private static bool IsReadTimeout(IOException error)
            {
                return error.InnerException is SocketException socket
                    && (socket.SocketErrorCode == SocketError.TimedOut || socket.SocketErrorCode == SocketError.WouldBlock);
            }

            private void Handle(string line, double receivedAt)
            {
                JObject obj = RpcRequest.ReadObject(line);
                int? id = RpcRequest.ReadId(obj);
                if (!id.HasValue) { diagnostic?.Invoke("Closing request without a valid ID"); Close(); return; }
                if (rejectBusy)
                {
                    Send(RpcReply.Error(id.Value, "SERVER_BUSY", "Another client owns the active session"));
                    Close();
                    return;
                }
                if (id.Value <= lastId)
                {
                    Send(RpcReply.Error(id.Value, "DUPLICATE_REQUEST_ID", "Request IDs must strictly increase",
                        new JObject { ["effect"] = "not_started" }));
                    return;
                }
                lastId = id.Value;
                RpcRequest request;
                try { request = RpcRequest.Parse(obj, id.Value, receivedAt); }
                catch (BridgeFault fault)
                {
                    fault.Details["effect"] = "not_started";
                    Send(RpcReply.Error(id.Value, fault.Code, fault.Message, fault.Details));
                    return;
                }
                if (Volatile.Read(ref inFlight) != null)
                {
                    Send(RpcReply.Error(request.Id, "REQUEST_IN_PROGRESS", "Wait for the previous response",
                        new JObject { ["effect"] = "not_started" }));
                    return;
                }
                if (request.Method == "bridge.hello")
                {
                    handshaken = true;
                    Send(RpcReply.Success(request.Id, RpcReply.Hello(sessionId, unityVersion)));
                    return;
                }
                if (!handshaken)
                {
                    Send(RpcReply.Error(request.Id, "HANDSHAKE_REQUIRED", "Call bridge.hello first",
                        new JObject { ["effect"] = "not_started" }));
                    return;
                }
                var work = new RpcWork(request);
                Interlocked.Exchange(ref inFlight, work);
                work.Completion.Task.ContinueWith(task =>
                {
                    // Clear before writing: a fast client may send its next request as soon as it reads the reply.
                    Interlocked.CompareExchange(ref inFlight, null, work);
                    if (!task.IsCanceled && !task.IsFaulted && !Closed) Send(task.Result);
                }, TaskScheduler.Default);
                if (Closed) { work.Cancel(); return; }
                if (!submit(work)) work.Completion.TrySetResult(RpcReply.Error(request.Id, "SERVER_BUSY",
                    "Main-thread operation slot is occupied", new JObject { ["effect"] = "not_started" }));
            }

            private void Send(JObject reply)
            {
                try
                {
                    byte[] bytes = Utf8.GetBytes(reply.ToString(Formatting.None) + "\n");
                    if (bytes.Length > MaxFrame + 1) { Close(); return; }
                    lock (writeGate)
                    {
                        if (Closed) return;
                        client.GetStream().Write(bytes, 0, bytes.Length);
                    }
                }
                catch (Exception error) when (error is IOException || error is SocketException || error is ObjectDisposedException)
                { Close(); }
            }

            internal void Close()
            {
                if (Interlocked.Exchange(ref closed, 1) != 0) return;
                Volatile.Read(ref inFlight)?.Cancel();
                client.Close();
                onClosed(this);
            }
        }
    }
}
