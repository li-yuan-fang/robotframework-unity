*** Settings ***
Resource    ../../resources/common.resource
Resource    ../../resources/login.resource
# 敏感信息统一管理
Resource    ../../configs/data.resource

*** Test Cases ***
Hello World
    Open Garupa

    Check Agreement
    Log To Console    \nAgreement OK

    Start GameView
    Log To Console    \nGameView Loaded

    Check Login
    Log To Console    \nLogin OK

    Sleep    30

    Close Garupa