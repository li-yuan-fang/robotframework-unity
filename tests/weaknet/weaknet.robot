*** Settings ***
Resource    ../../resources/common.resource
Resource    ../../resources/network.resource
Resource    ../../resources/overlay.resource
Library    AppiumLibrary

*** Variables ***
${IMAGE_DIR}    ${CURDIR}/../../assets/buttons

*** Test Cases ***
Wait Main Scene
    Open Garupa App
    Log To Console    \nOpen Application OK

    Switch To Context    OCR
    ${ocr_xml}=    Get Source
    Log To Console    \n===== OCR 原始 XML =====\n${ocr_xml}
    Switch To Context    NATIVE_APP

    # OCR Text Should Exist
    # Check Activity Overlay