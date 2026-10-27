*** Settings ***
Resource    ./vision.resource

*** Keywords ***
Check Agreement
    TRY
        Wait Activity    com.base.gsc_agreement_library.AgreementWebActivity    5
    EXCEPT    TimeoutException    type=START
        RETURN
    END
    Accept Agreement

Accept Agreement
    ${btn_accept}=    Set Variable     xpath=//android.widget.TextView[@text="同意"]
    Expect Element    ${btn_accept}    visible    10
    Click Element    ${btn_accept}

Login
    ${login_by_password}=    Set Variable
...     xpath=//android.widget.ImageView[@resource-id="com.bilibili.star.bili:id/iv_gsc_account_login"]
    Expect Element    ${login_by_password}    visible    10
    Click Element    ${login_by_password}

    ${btn_accept}=    Set Variable
...     xpath=//android.widget.TextView[@resource-id="com.bilibili.star.bili:id/tv_gs_dialog_onekey_submit"]
    Expect Element    ${btn_accept}    visible    10
    Click Element    ${btn_accept}

    ${input_username}=    Set Variable
...     xpath=//android.widget.EditText[@resource-id="com.bilibili.star.bili:id/et_gsc_account"]
    ${input_password}=    Set Variable
...     xpath=//android.widget.EditText[@resource-id="com.bilibili.star.bili:id/et_gsc_account_pwd"]
    Expect Element    ${input_username}    visible    10
    Input Text    ${input_username}    ${USER_NAME}
    Expect Element    ${input_password}    visible    10
    Input Text    ${input_password}    ${USER_PASSWORD}

    ${btn_login}=    Set Variable
...     xpath=//android.widget.TextView[@resource-id="com.bilibili.star.bili:id/tv_gsc_account_login"]
    Expect Element    ${btn_login}    visible    10
    Click Element    ${btn_login}

    Wait Until Keyword Succeeds    30s    1s    Try OCR Click    哔哩安卓

Check Login
    TRY
        Wait Activity    com.gsc.phone_login.PhoneLoginActivity    5
    EXCEPT    TimeoutException    type=START
        RETURN
    END
    Login

Start GameView
    Wait Activity    .MainActivity    20
    Expect Element    xpath=//android.view.View[@content-desc="Game view"]    visible    20
    Wait Until Keyword Succeeds    30s    1s    Try OCR Click    START
