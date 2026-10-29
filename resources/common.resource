*** Settings ***
Library    AppiumLibrary

Resource    ./login.resource
Resource    ./overlay.resource
# 敏感信息统一管理
Resource    ../configs/data.resource

*** Variables ***
${APPIUM_URL}        http://localhost:4723
${ADB_DEVICE}        emulator-5554
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
    # ...    appium:settings[ocrLanguage]=chi_sim+eng
    # 实测发现中文OCR准确性太低
    ...    appium:settings[ocrInvertColors]=${True}

Open Garupa
    Open Garupa App

    Check Agreement
    Log To Console    \nAgreement OK

    Wait GameView
    Log To Console    \nGameView Loaded

    Check Login
    Log To Console    \nLogin OK

    Check Activity Overlay
    Log To Console    \nOverlay Checked

Close Garupa
    Terminate Application    ${APP_PACKAGE}
