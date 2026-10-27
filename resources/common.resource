*** Settings ***
Library    AppiumLibrary

Resource    ./login.resource
# 敏感信息统一管理
Resource    ../configs/data.resource

*** Variables ***
${APPIUM_URL}        http://localhost:4723
${ADB_DEVICE}        device
${APP_PATH}          ${CURDIR}/../BanG Dream!.apk
${APP_PACKAGE}       com.bilibili.star.bili
${APP_ACTIVITY}      com.bilibili.star.bili.PermissionActivity

*** Keywords ***
Open Garupa App
    [Arguments]    ${reset}=${False}
    ${reset_str}=    Evaluate    str(${reset}).lower()
    ${no_reset_str}=    Evaluate    str(not ${reset}).lower()
    Open Application    ${APPIUM_URL}
    ...    platformName=Android
    ...    deviceName=${ADB_DEVICE}
    ...    app=${APP_PATH}
    ...    appPackage=${APP_PACKAGE}
    ...    appActivity=${APP_ACTIVITY}
    ...    automationName=UiAutomator2
    ...    noReset=${no_reset_str}
    ...    fullReset=${reset_str}
    ...    noSign=${no_reset_str}

Open Garupa
    Open Garupa App

    Check Agreement
    Log To Console    \nAgreement OK

    Wait GameView
    Log To Console    \nGameView Loaded

    Check Login
    Log To Console    \nLogin OK

Close Garupa
    Terminate Application    ${APP_PACKAGE}
