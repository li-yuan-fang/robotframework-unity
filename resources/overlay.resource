*** Settings ***
Resource    ./vision.resource

*** Keywords ***
Check Story Overlay
    ${text_menu}=    Set Variable    菜单
    ${text_skip}=    Set Variable    跳过
    ${exists}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_menu}
    IF    not(${exists})
        RETURN
    END

    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_menu}
    Sleep    3
    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_skip}
    Sleep    3
    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_skip}

Check Activity Popup Overlay
    ${text_next}=    Set Variable    下一步
    ${text_close}=    Set Variable    关闭

    ${exists_next}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_next}
    ${exists_close}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_close}
    WHILE    ${exists_next} or ${exists_close}
        IF    ${exists_next}
            Wait Until Keyword Succeeds    40s    500ms    Try OCR Click    ${text_next}
        ELSE IF    ${exists_close}
            Wait Until Keyword Succeeds    40s    500ms    Try OCR Click    ${text_close}
        END

        Sleep    3

        ${exists_next}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_next}
        ${exists_close}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_close}
    END
