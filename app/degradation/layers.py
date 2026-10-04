from enum import StrEnum


class OnionLayer(StrEnum):
    HUMAN_OPERATOR = 'human_operator'
    LOCAL_RECORDS = 'local_records'
    MAPS_MISSION = 'maps_mission'
    POSITIONING = 'positioning'
    NETWORK_TRANSPORT = 'network_transport'
    TAK_COLLABORATION = 'tak_collaboration'
    CLOUD_SYNC = 'cloud_sync'
    AI_AUTOMATION = 'ai_automation'

