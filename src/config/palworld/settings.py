#!/usr/bin/env python3
"""
Direct Palworld settings classes with INI key names for automatic conversion
"""

from dataclasses import dataclass


@dataclass
class PalworldSettings:
    """Direct Palworld settings with INI key names for automatic conversion"""

    ServerName: str = "Palworld Server"
    ServerDescription: str = "A Palworld dedicated server"
    AdminPassword: str = "admin123"
    ServerPassword: str = ""
    PublicPort: int = 8211
    PublicIP: str = ""
    ServerPlayerMaxNum: int = 32
    CoopPlayerMaxNum: int = 4

    RESTAPIEnabled: bool = True
    RESTAPIPort: int = 8212
    RCONEnabled: bool = True
    RCONPort: int = 25575

    bUseAuth: bool = True
    Region: str = ""
    BanListURL: str = "https://api.palworldgame.com/api/banlist.txt"

    Difficulty: str = "None"
    bIsMultiplay: bool = True
    bIsPvP: bool = False
    bHardcore: bool = False
    DeathPenalty: str = "All"

    RandomizerType: str = "None"
    RandomizerSeed: str = ""
    bIsRandomizerPalLevelRandom: bool = False

    DayTimeSpeedRate: float = 1.0
    NightTimeSpeedRate: float = 1.0
    ExpRate: float = 1.0
    WorkSpeedRate: float = 1.0

    PalCaptureRate: float = 1.0
    PalSpawnNumRate: float = 1.0
    PalDamageRateAttack: float = 1.0
    PalDamageRateDefense: float = 1.0
    PalStomachDecreaceRate: float = 1.0
    PalStaminaDecreaceRate: float = 1.0
    PalAutoHPRegeneRate: float = 1.0
    PalAutoHpRegeneRateInSleep: float = 1.0
    PalEggDefaultHatchingTime: float = 72.0

    PlayerDamageRateAttack: float = 1.0
    PlayerDamageRateDefense: float = 1.0
    PlayerStomachDecreaceRate: float = 1.0
    PlayerStaminaDecreaceRate: float = 1.0
    PlayerAutoHPRegeneRate: float = 1.0
    PlayerAutoHpRegeneRateInSleep: float = 1.0

    bEnablePlayerToPlayerDamage: bool = False
    bEnableFriendlyFire: bool = False
    bEnableInvaderEnemy: bool = True

    BuildObjectHpRate: float = 1.0
    BuildObjectDamageRate: float = 1.0
    BuildObjectDeteriorationDamageRate: float = 1.0
    CollectionDropRate: float = 1.0
    CollectionObjectHpRate: float = 1.0
    CollectionObjectRespawnSpeedRate: float = 1.0
    bBuildAreaLimit: bool = False
    MaxBuildingLimitNum: int = 0
    EnemyDropItemRate: float = 1.0

    BaseCampMaxNum: int = 128
    BaseCampWorkerMaxNum: int = 15
    BaseCampMaxNumInGuild: int = 4

    GuildPlayerMaxNum: int = 20
    bAutoResetGuildNoOnlinePlayers: bool = False
    AutoResetGuildTimeNoOnlinePlayers: float = 72.0

    DropItemMaxNum: int = 3000
    DropItemMaxNum_UNKO: int = 100
    DropItemAliveMaxHours: float = 1.0
    ItemWeightRate: float = 1.0
    EquipmentDurabilityDamageRate: float = 1.0

    bActiveUNKO: bool = False
    bEnableAimAssistPad: bool = True
    bEnableAimAssistKeyboard: bool = False
    bCanPickupOtherGuildDeathPenaltyDrop: bool = False
    bEnableNonLoginPenalty: bool = True
    bEnableFastTravel: bool = True
    bIsStartLocationSelectByMap: bool = True
    bExistPlayerAfterLogout: bool = False
    bEnableDefenseOtherGuildPlayer: bool = False
    bInvisibleOtherGuildBaseCampAreaFX: bool = False

    AutoSaveSpan: float = 30.0
    bIsUseBackupSaveData: bool = True

    bShowPlayerList: bool = False
    ChatPostLimitPerMinute: int = 30

    bPalLost: bool = False
    bCharacterRecreateInHardcore: bool = False

    LogFormatType: str = "Text"

    SupplyDropSpan: int = 180
    EnablePredatorBossPal: bool = True

    CrossplayPlatforms: str = "(Steam,Xbox,PS5,Mac)"

    bAllowGlobalPalboxExport: bool = True
    bAllowGlobalPalboxImport: bool = False

    ServerReplicatePawnCullDistance: float = 15000.0
    ItemContainerForceMarkDirtyInterval: float = 1.0

    # New settings
    bAllowClientMod: bool = True
    bEnableFastTravelOnlyBaseCamp: bool = False
    PhysicsActiveDropItemMaxNum: int = -1

    # Server management
    bEnableBuildingPlayerUIdDisplay: bool = False
    bIsShowJoinLeftMessage: bool = True

    # Features - Stat allocation
    bAllowEnhanceStat_Attack: bool = True
    bAllowEnhanceStat_Health: bool = True
    bAllowEnhanceStat_Stamina: bool = True
    bAllowEnhanceStat_Weight: bool = True
    bAllowEnhanceStat_WorkSpeed: bool = True

    # Features - PvP map display
    bDisplayPvPItemNumOnWorldMap_BaseCamp: bool = False
    bDisplayPvPItemNumOnWorldMap_Player: bool = False

    # Features - Voice chat
    bEnableVoiceChat: bool = False
    VoiceChatMaxVolumeDistance: float = 3000.0
    VoiceChatZeroVolumeDistance: float = 15000.0

    # Game balances - PvP additional drops
    bAdditionalDropItemWhenPlayerKillingInPvPMode: bool = False
    AdditionalDropItemWhenPlayerKillingInPvPMode: str = "PlayerDropItem"
    AdditionalDropItemNumWhenPlayerKillingInPvPMode: int = 1

    # Game balances - Respawn penalties
    BlockRespawnTime: float = 5.0
    RespawnPenaltyDurationThreshold: float = 0.0
    RespawnPenaltyTimeScale: float = 2.0

    # Game balances - Guild
    GuildRejoinCooldownMinutes: float = 0

    # Game balances - Other
    DenyTechnologyList: str = ""
    ItemCorruptionMultiplier: float = 1.0
    MonsterFarmActionSpeedRate: float = 1.0

    # v1.0.0 - Player data storage
    PlayerDataPalStorageUpdateCheckTickInterval: float = 1.0

    # v1.0.0 - Guild auto-transfer
    AutoTransferMasterCheckIntervalSeconds: float = 3600.0
    AutoTransferMasterThresholdDays: int = 14

    # v1.0.0 - Guild processing
    MaxGuildsPerFrame: int = 10

    # v1.0.0 - Building name display cache
    BuildingNameDisplayCacheTTLSeconds: int = 60
