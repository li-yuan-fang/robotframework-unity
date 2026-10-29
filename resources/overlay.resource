*** Settings ***
Library    AppiumLibrary
Resource    ./vision.resource

*** Variables ***
${ASSETS_BTN_DIR}    ${CURDIR}/../assets/buttons

*** Keywords ***
Check Story Overlay
    ${path_menu}=    Set Variable    ${ASSETS_BTN_DIR}/story_menu.png
    ${path_skip}=    Set Variable    ${ASSETS_BTN_DIR}/story_skip.png
    ${path_skip_active}=    Set Variable    ${ASSETS_BTN_DIR}/skip_active.png
    ${result}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_menu}
    IF    '${result}[0]' == 'FAIL'
        RETURN    ${False}
    END

    CV Click Image Element    ${result}[1]
    Sleep    2

    # 此时已确定出于剧情中 如果检测不到按钮直接报错
    ${element}=    CV Find Image Element    ${path_skip}
    CV Click Image Element    ${element}
    Sleep    2
    ${element}=    CV Find Image Element    ${path_skip_active}
    CV Click Image Element    ${element}
    RETURN    ${True}

Check Activity Popup Overlay
    ${path_next}=    Set Variable    ${ASSETS_BTN_DIR}/next.png
    ${path_next_active}=    Set Variable    ${ASSETS_BTN_DIR}/next_active.png
    ${path_close}=    Set Variable    ${ASSETS_BTN_DIR}/close.png

    ${element_next}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_next}
    ${element_next_active}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_next_active}
    ${element_close}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_close}
    IF    ('${element_next}[0]' == 'FAIL') and ('${element_next_active}[0]' == 'FAIL') and ('${element_close}[0]' == 'FAIL')
        Log To Console    No Match
        RETURN    ${False}
    END

    WHILE    ('${element_next}[0]' == 'PASS') or ('${element_next_active}[0]' == 'PASS') or ('${element_close}[0]' == 'PASS')
        IF    '${element_next}[0]' == 'PASS'
            CV Click Image Element    ${element_next}[1]
        ELSE IF    '${element_next_active}[0]' == 'PASS'
            CV Click Image Element    ${element_next_active}[1]
        ELSE IF    '${element_close}[0]' == 'PASS'
            CV Click Image Element    ${element_close}[1]
        END

        Sleep    3

        ${element_next}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_next}
        ${element_next_active}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_next_active}
        ${element_close}=    Run Keyword And Ignore Error    CV Find Image Element    ${path_close}
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
    ${path_live}=    Set Variable    ${ASSETS_BTN_DIR}/live.png

    ${exists}=    Run Keyword And Return Status    CV Find Image Element    ${path_live}
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

        ${exists}=    Run Keyword And Return Status    CV Find Image Element    ${path_live}
    END
