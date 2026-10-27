*** Settings ***
Library           ../python/UnityBridge.py
Suite Setup       Connect Demo
Suite Teardown    Close Unity Connection

*** Variables ***
${MODE}             editor
${DEVICE_SERIAL}    ${None}
${SERVER_PORT}      13000

*** Keywords ***
Connect Demo
    IF    '${MODE}' == 'android'
        Connect To Unity    serial=${DEVICE_SERIAL}    server_port=${SERVER_PORT}
    ELSE IF    '${MODE}' == 'editor'
        Connect To Unity Editor    server_port=${SERVER_PORT}
    ELSE
        Fail    MODE must be editor or android
    END

*** Test Cases ***
Four State Conditions And One Click
    Wait For Unity Element State    demo.login    visible
    Wait For Unity Element State    demo.login    enabled
    Wait For Unity Element State    demo.hidden    not visible
    Wait For Unity Element State    demo.hidden    enabled
    Wait For Unity Element State    demo.purchase    disabled
    Click Unity Element    demo.toggle
    Wait For Unity Element State    demo.purchase    enabled
    Click Unity Element    demo.once
    Wait For Unity Element State    demo.once    disabled
    Click Unity Element    demo.login
    Wait For Unity Element State    demo.login    not visible
    Wait For Unity Element State    demo.home    visible

Blocked Element Must Time Out
    Run Keyword And Expect Error    *ELEMENT_CLICK_TIMEOUT*    Click Unity Element    demo.blocked    timeout=300ms

Missing Element Is Hidden But Is Not Disabled
    Wait For Unity Element State    demo.does_not_exist    not visible
    Run Keyword And Expect Error    *ELEMENT_WAIT_TIMEOUT*    Wait For Unity Element State    demo.does_not_exist    disabled    timeout=300ms
