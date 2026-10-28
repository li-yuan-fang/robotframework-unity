*** Settings ***
Library    AppiumLibrary
Resource    ./vision.resource

*** Keywords ***
Check Story Overlay
    ${text_menu}=    Set Variable    菜单
    ${text_skip}=    Set Variable    跳过
    ${exists}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_menu}
    IF    not(${exists})
        RETURN    ${False}
    END

    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_menu}
    Sleep    3
    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_skip}
    Sleep    3
    Wait Until Keyword Succeeds    10s    1s    Try OCR Click    ${text_skip}
    RETURN    ${True}

Check Activity Popup Overlay
    ${text_next}=    Set Variable    下一步
    ${text_close}=    Set Variable    关闭

    ${exists_next}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_next}
    ${exists_close}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_close}
    IF    not(${exists_next}) and not(${exists_close})
        RETURN    ${False}
    END

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
    RETURN    ${True}

Click Center
    ${width}=     Get Window Width
    ${height}=    Get Window Height

    ${center_x}=    Evaluate    int(${width} * 0.5)
    ${center_y}=    Evaluate    int(${height} * 0.5)

    ${center_point}=    Create List    ${center_x}    ${center_y}
    ${points}=    Create List    ${center_point}

    Tap With Positions    300ms    @{points}

Check Activity Overlay
    ${text_live}=    Set Variable    演出

    ${exists}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_live}
    WHILE    not(${exists})
        ${result_story}=    Check Story Overlay
        IF    ${result_story}    Sleep    3
        ${result_activity}=    Check Activity Popup Overlay
        IF    ${result_activity}    Sleep    3

        IF    not(${result_story}) and not(${result_activity})
            # 这种情况一般是新卡面广告
            Sleep    20
            Click Center
            Sleep    5
        END

        ${exists}=    Run Keyword And Return Status    OCR Text Should Exist    ${text_live}
    END
