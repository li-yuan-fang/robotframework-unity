*** Settings ***
Library    AppiumLibrary
Library    ../libraries/opencv_vision/OpenCVVision.py

*** Keywords ***
Try OCR Click
    [Arguments]    ${target_text}
    [Setup]    Switch To Context    OCR
    [Teardown]    Switch To Context    NATIVE_APP
    Click Element    xpath=//*[contains(text(), '${target_text}')]

OCR Text Should Exist
    [Arguments]    ${target_text}
    [Setup]    Switch To Context    OCR
    [Teardown]    Switch To Context    NATIVE_APP
    Page Should Contain Element    xpath=//*[contains(text(), '${target_text}')]

Check OCR Text
    [Arguments]    @{keywords}
    [Setup]    Switch To Context    OCR
    [Teardown]    Switch To Context    NATIVE_APP
    FOR    ${key}    IN    @{keywords}
        ${exists}=    Run Keyword And Return Status
        ...    Page Should Contain Element
        ...    xpath=//*[contains(text(), '${key}')]
        IF    ${exists}
            RETURN    ${True}
        END
    END
    RETURN    ${False}

CV Click Image Element
    [Arguments]    ${element}    ${duration}=300ms
    ${center_x}=    Evaluate    int(${element.rect}[x] + ${element.size}[width] / 2)
    ${center_y}=    Evaluate    int(${element.rect}[y] + ${element.size}[height] / 2)

    ${center}=    Create List    ${center_x}    ${center_y}
    @{postions}=    Create List    ${center}

    Tap With Positions    ${duration}    @{postions}

# Find Image Element
#     [Arguments]    ${image_path}    ${threshold}=0.5
#     Switch To Context    NATIVE_APP

#     ${library}=    Get Library Instance    AppiumLibrary
#     ${driver}=    Call Method    ${library}    _current_application

#     ${template}=    Evaluate
#     ...    base64.b64encode(pathlib.Path($image_path).read_bytes()).decode("ascii")
#     ...    modules=base64,pathlib

#     ${threshold}=    Convert To Number    ${threshold}
#     ${settings}=    Create Dictionary    imageMatchThreshold=${threshold}
#     Call Method    ${driver}    update_settings    ${settings}

#     ${element}=    Call Method    ${driver}    find_element    -image    ${template}
#     RETURN    ${element}

# Try Image Click
#     [Arguments]    ${image_path}    ${threshold}=0.6
#     ${element}=    Find Image Element    ${image_path}    ${threshold}

#     # 要求图片尺寸严格一致 实际可行性低 可能需要引入OpenCV识别
#     ${rect}=    Evaluate    $element.rect
#     ${x}=    Set Variable    ${rect}[x]
#     ${y}=    Set Variable    ${rect}[y]
#     ${width}=    Set Variable    ${rect}[width]
#     ${height}=    Set Variable    ${rect}[height]

#     ${w}=     Get Window Width
#     ${h}=    Get Window Height
#     Log To Console    Pos:(${x}, ${y}), Size:${width} × ${height}

#     Call Method    ${element}    click
