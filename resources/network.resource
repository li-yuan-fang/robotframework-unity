*** Settings ***
Library    Process
Resource    ./common.resource

*** Keywords ***
Run Network Command
    [Arguments]    @{args}
    ${result}=    Run Process
    ...    adb    -s    ${ADB_DEVICE}    emu    network    @{args}
    ...    timeout=15s    on_timeout=terminate

    Should Be Equal As Integers    ${result.rc}    0
    Should Not Contain    ${result.stdout}    KO:

Set Weak Network
    Run Network Command    speed    128    512
    Run Network Command    delay    100    300

Recover Weak Network
    TRY
        Run Network Command    speed    full
    FINALLY
        Run Network Command    delay    none
    END

Pause Network
    [Arguments]    ${seconds}=5
    ${seconds}=    Convert To Integer    ${seconds}
    Should Be True    $seconds > 0

    ${command}=    Set Variable    echo sleep ${seconds} > /data/local/tmp/wifi_restore.sh; echo svc wifi enable >> /data/local/tmp/wifi_restore.sh; nohup sh /data/local/tmp/wifi_restore.sh </dev/null 2>&1 & svc wifi disable
    Run Keyword And Ignore Error    Run Process    adb    -s    ${ADB_DEVICE}    shell    ${command}    timeout=${seconds}s