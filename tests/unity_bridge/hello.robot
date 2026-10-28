*** Settings ***
Library    ${CURDIR}/../../bridge/python/UnityBridge.py
Library    AppiumLibrary

*** Variables ***
${APPIUM_URL}        http://localhost:4723
${ADB_DEVICE}        127.0.0.1:5555
${APP_PATH}          ${CURDIR}/../../Test2D.apk
${APP_PACKAGE}       com.DefaultCompany.Test2D
${APP_ACTIVITY}      com.unity3d.player.UnityPlayerGameActivity

*** Test Cases ***
Start Game
    Open Application    ${APPIUM_URL}
    ...    platformName=Android
    ...    deviceName=${ADB_DEVICE}
    ...    app=${APP_PATH}
    ...    appPackage=${APP_PACKAGE}
    ...    appActivity=${APP_ACTIVITY}
    ...    automationName=UiAutomator2

Test Unity Bridge
    [Setup]    Connect To Unity    serial=${ADB_DEVICE}    server_port=13000    timeout=30s
    [Teardown]    Close Unity Connection
    ${btn_jump}=    test.jump
    Wait For Unity Element State    ${btn_jump}    visible    timeout=10s
    FOR    ${index}    IN RANGE    10
        Click Unity Element    ${btn_jump}    timeout=5s
        Sleep    2
    END

End Game
    Terminate Application    ${APP_PACKAGE}
