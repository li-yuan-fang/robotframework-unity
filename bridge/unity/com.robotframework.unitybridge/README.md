# Unity Bridge Demo SDK

Use **Package Manager → Add package from disk** and select this package's `package.json`.

For an existing scene, add **GameObject → Unity Bridge → SDK Host** and attach **Bridge Element** to the same GameObject as each Button/Toggle. Set a unique Element Id in the Inspector. The host starts a loopback TCP server in the Editor and Development Builds.

For a self-contained scene, import **UGUI Bridge Demo** from this package's Samples, then use **Tools → Unity Bridge → Create Demo Scene** and enter Play Mode.

Requires Unity 2021.3+, UGUI, and Unity's Newtonsoft JSON package. Android builds need Internet Access set to Require and Development Build enabled. The default server port is 13000.

The complete Chinese integration guide, Python entry point, Robot example, and validation limits are in the repository's `bridge/README.md`. This is a Button/Toggle automation prototype; rendering and Android integration must be verified in a real Unity project.
