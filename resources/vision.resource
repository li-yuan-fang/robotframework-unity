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
