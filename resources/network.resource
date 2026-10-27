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
