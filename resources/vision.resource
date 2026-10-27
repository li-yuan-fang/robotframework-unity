*** Settings ***
Library    AppiumLibrary

*** Keywords ***
Try OCR Click
    [Arguments]    ${target_text}
    [Setup]    Switch To Context    OCR
    [Teardown]    Switch To Context    NATIVE_APP
    Click Element    xpath=//*[contains(text(), '${target_text}')]
