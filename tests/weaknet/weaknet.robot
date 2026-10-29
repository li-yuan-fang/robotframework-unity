*** Settings ***
Resource    ../../resources/common.resource
Resource    ../../resources/network.resource

Suite Teardown    Recover Weak Network

*** Test Cases ***
Limit Network
    Set Weak Network

Start Game
    Open Garupa
