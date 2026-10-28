*** Settings ***
Resource    ../../resources/common.resource
Library    ../../libraries/opencv_vision/OpenCVVision.py
Library    AppiumLibrary

*** Test Cases ***
Hello CV
    Open Garupa App
    Log To Console    \nOpen Application OK

    ${width}=     Get Window Width
    ${height}=    Get Window Height

    ${center_x}=    Evaluate    int(${width} * 0.5)
    ${center_y}=    Evaluate    int(${height} * 0.5)

    ${region}=    Create List    ${center_x}    ${center_y}    ${center_x}    ${center_y}

    Capture Page Screenshot    ${CURDIR}/snapshot.png
    ${element}=    CV Find Image Element    ${CURDIR}/testcv.png    roi=${region}
    Log To Console    \n(${element.rect}[x], ${element.rect}[y]) size:(${element.size}[width], ${element.size}[height])
