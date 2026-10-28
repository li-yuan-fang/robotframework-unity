*** Settings ***
Library    ${CURDIR}/FixtureAppium.py    WITH NAME    Device
Library    ${CURDIR}/../OpenCVVision.py

*** Test Cases ***
Find A Template From Memory
    ${template}=    Get Fixture Template
    ${element}=    CV Find Image Element    ${template}    appium_library=Device    coordinate_mode=full_window
    Should Be Equal As Integers    ${element.rect}[x]    81
    Should Be Equal As Integers    ${element.rect}[y]    63
    Should Be Equal As Integers    ${element.size}[width]    48
    Should Be Equal As Numbers    ${element.center}[x]    105
    Should Be Equal    ${element.coordinate_mapping}    identity
    ${count}=    Get Fixture Capture Count
    Should Be Equal As Integers    ${count}    1

Search Within A Region
    ${template}=    Get Fixture Template
    ${region}=    Create List    60    40    120    100
    ${element}=    CV Find Image Element    ${template}    appium_library=Device    roi=${region}
    Should Be Equal As Integers    ${element.location}[x]    81
    Should Be Equal As Integers    ${element.location}[y]    63
    Should Be Equal    ${element.coordinate_mapping}    unverified

Robot Converts ROI From A List Variable Or Text
    ${template}=    Get Fixture Template
    ${region}=    Create List    60    40    120    100
    ${as_list}=    CV Find Image Element    ${template}    appium_library=Device    roi=${region}
    ${as_text}=    CV Find Image Element    ${template}    appium_library=Device
    ...    roi=[60, 40, 120, 100]    debug=on_failure
    Even Keyword Arguments Stay Typed    ${template}    ${region}    appium_library=Device
    Should Be Equal    ${as_text.roi}    ${as_list.roi}
    Should Be Equal As Integers    ${as_text.location}[x]    81

Invalid Arguments Keep Their Error Code
    ${template}=    Get Fixture Template
    Run Keyword And Expect Error    *INVALID_ARGUMENT*
    ...    CV Find Image Element    ${template}    appium_library=Device    roi=[1, 2, 32768, 4]

Missing Session Keeps Its Error Code
    ${template}=    Get Fixture Template
    Run Keyword And Expect Error    *APPIUM_SESSION_ERROR*
    ...    CV Find Image Element    ${template}    appium_library=Missing

Repeated Targets Are Ambiguous
    Use Duplicate Targets
    ${template}=    Get Fixture Template
    Run Keyword And Expect Error    *AMBIGUOUS_IMAGE_MATCH*
    ...    CV Find Image Element    ${template}    appium_library=Device

*** Keywords ***
Even Keyword Arguments Stay Typed
    [Arguments]    ${template}    ${region}    ${appium_library}=AppiumLibrary
    ${element}=    CV Find Image Element    ${template}    appium_library=${appium_library}
    ...    roi=${region}
    Should Be Equal As Integers    ${element.rect}[width]    48
