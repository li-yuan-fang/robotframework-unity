*** Settings ***
Resource    ../../resources/common.resource
Resource    ../../resources/network.resource

Suite Setup    Open Garupa

*** Test Cases ***
Loss Test
    # 实体机没办法直接调整网络 可能需要引入外部网络工具再测限速/延迟调整
    Pause Network    5
    Sleep    10
    Pause Network    10
