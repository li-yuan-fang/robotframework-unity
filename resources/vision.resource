*** Settings ***
Library    AppiumLibrary

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

Find Image Element
    [Arguments]    ${image_path}    ${threshold}=0.8
    Switch To Context    NATIVE_APP

    ${library}=    Get Library Instance    AppiumLibrary
    ${driver}=    Call Method    ${library}    _current_application

    ${template}=    Evaluate
    ...    base64.b64encode(pathlib.Path($image_path).read_bytes()).decode("ascii")
    ...    modules=base64,pathlib

    ${threshold}=    Convert To Number    ${threshold}
    ${settings}=    Create Dictionary    imageMatchThreshold=${threshold}
    Call Method    ${driver}    update_settings    ${settings}

    ${element}=    Call Method    ${driver}    find_element    -image    ${template}
    RETURN    ${element}

Try Image Click
    [Arguments]    ${image_path}    ${threshold}=0.8
    ${element}=    Find Image Element    ${image_path}    ${threshold}
    Call Method    ${element}    click
