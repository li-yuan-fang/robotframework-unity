*** Settings ***
Resource    ../../resources/common.resource

*** Test Cases ***
Hello World
    [Setup]    Open Garupa
    [Teardown]    Close Garupa
    Sleep    30
