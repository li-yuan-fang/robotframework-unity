*** Settings ***
Library    AppiumLibrary

*** Variables ***
${APPIUM_URL}        http://localhost:4723
${ADB_DEVICE}        device
${APP_PATH}          ${CURDIR}/../BanG Dream!.apk
${APP_PACKAGE}       com.bilibili.star.bili
${APP_ACTIVITY}      com.bilibili.star.bili.PermissionActivity

*** Keywords ***
Open Garupa
    Open Application    ${APPIUM_URL}
    ...    platformName=Android
    ...    deviceName=${ADB_DEVICE}
    ...    app=${APP_PATH}
    ...    appPackage=${APP_PACKAGE}
    ...    appActivity=${APP_ACTIVITY}
    ...    automationName=UiAutomator2
    ...    noReset=true
    ...    fullReset=false
    ...    noSign=true

Close Garupa
    Terminate Application    ${APP_PACKAGE}

