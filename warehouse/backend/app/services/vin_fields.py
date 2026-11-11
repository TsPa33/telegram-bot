"""Bounded useful VIN attributes, not an exhaustive vPIC schema or factory BOM."""
PRIMARY={
 'EngineCode':'engine_code','Generation':'generation','TransmissionCode':'transmission_code',
 'Make':'manufacturer','Model':'model','ModelYear':'year','EngineModel':'engine',
 'DisplacementL':'engine_displacement_l','FuelTypePrimary':'fuel_type','FuelTypeSecondary':'fuel_secondary',
 'TransmissionStyle':'transmission','TransmissionSpeeds':'transmission_speeds',
 'DriveType':'drive_type','BodyClass':'body_class','Trim':'trim','Trim2':'trim_secondary',
 'PlantCountry':'plant_country','PlantCity':'plant_city','PlantCompanyName':'plant_company',
 'EngineCylinders':'engine_cylinders','EngineKW':'engine_power_kw','EngineHP':'engine_power_hp',
 'Doors':'doors','Series':'series','Series2':'series_secondary','VehicleType':'vehicle_type',
 'ElectrificationLevel':'electrification','EngineManufacturer':'engine_manufacturer',
 'DestinationMarket':'market','EngineConfiguration':'engine_configuration','FuelInjectionType':'fuel_injection',
}
# Exact labels are centrally returned by the backend; raw identifiers remain unchanged.
EXTRA={
 'Manufacturer':('manufacturer_company','Компанія-виробник'),
 'DisplacementCC':('displacement_cc','Об’єм двигуна, см³'),
 'ValveTrainDesign':('valve_train','Клапанний механізм'),
 'Turbo':('turbo','Турбонаддув'), 'CoolingType':('cooling','Тип охолодження'),
 'EngineCycles':('engine_cycles','Кількість тактів двигуна'),
 'EngineHP_to':('power_hp_to','Верхня межа потужності, к.с.'),
 'EngineKW_to':('power_kw_to','Верхня межа потужності, кВт'),
 'WheelBaseType':('wheelbase_type','Тип колісної бази'),
 'WheelBaseShort':('wheelbase_short_inches','Колісна база, дюйми'),
 'WheelBaseLong':('wheelbase_long_inches','Довга колісна база, дюйми'),
 'WheelSizeFront':('wheel_front_inches','Передні колеса, дюйми'),
 'WheelSizeRear':('wheel_rear_inches','Задні колеса, дюйми'),
 'BrakeSystemType':('brake_system','Гальмівна система'),
 'BrakeSystemDesc':('brake_description','Опис гальмівної системи'),
 'SteeringLocation':('steering_location','Розташування керма'),
 'Axles':('axles','Осі'), 'Seats':('seats','Місця'), 'SeatRows':('seat_rows','Ряди сидінь'),
 'BatteryType':('battery_type','Тип акумулятора'),
 'BatteryV':('battery_voltage','Напруга акумулятора, В'),
 'BatteryKWh':('battery_kwh','Ємність батареї, кВт·год'),
 'ChargerPowerKW':('charger_kw','Потужність заряджання, кВт'),
 'EVDriveUnit':('ev_drive_unit','Електричний приводний модуль'),
 'TPMS':('tpms','Контроль тиску шин'), 'ABS':('abs','ABS'),
}
PRIMARY_KEYS=set(PRIMARY.values())|{'generation','engine_code','transmission_code','market'}
EXTRA_KEYS={key for key,label in EXTRA.values()}
IMPORTANT={'manufacturer','model','year','body_class','engine','engine_code','engine_displacement_l','engine_power_kw','fuel_type','transmission','transmission_speeds','drive_type','doors'}
# Not all vehicles have a separate engine code, and series is not generation.
CATALOGUE_KEYS=IMPORTANT|{'generation','series','trim','engine_cylinders','electrification','fuel_secondary','engine_configuration','engine_manufacturer','fuel_injection','transmission_code'}


def present(value):
    return value is not None and str(value).strip().casefold() not in ('','null','none','not applicable','n/a','not available','unknown','not provided','nan','inf','infinity','-inf')
