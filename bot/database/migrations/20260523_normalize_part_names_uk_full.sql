-- Ensure canonical Ukrainian part template names and previously generated seller part names.

WITH name_map(en_name, uk_name) AS (
    VALUES
    ('Front panel','Передня панель'),
    ('Hood lock','Замок капота'),
    ('Left side skirt','Лівий поріг'),
    ('Right side skirt','Правий поріг'),
    ('Radiator support','Телевізор'),
    ('Roof','Дах'),
    ('Tailgate','Кришка багажника'),
    ('Left fog light','Ліва протитуманна фара'),
    ('Right fog light','Права протитуманна фара'),
    ('Left turn signal','Лівий поворотник'),
    ('Right turn signal','Правий поворотник'),
    ('AC compressor','Компресор кондиціонера'),
    ('Alternator','Генератор'),
    ('Cylinder head','Головка блоку циліндрів'),
    ('EGR valve','Клапан EGR'),
    ('Engine block','Блок двигуна'),
    ('Engine mount','Подушка двигуна'),
    ('Exhaust manifold','Випускний колектор'),
    ('Flywheel','Маховик'),
    ('High-pressure fuel pump','Паливний насос високого тиску'),
    ('Injector','Форсунка'),
    ('Intake manifold','Впускний колектор'),
    ('Starter','Стартер'),
    ('Throttle body','Дросельна заслінка'),
    ('Axle shaft','Піввісь'),
    ('Clutch','Зчеплення'),
    ('Differential','Диференціал'),
    ('Driveshaft','Карданний вал'),
    ('Gear shifter assembly','Механізм перемикання передач'),
    ('Left drive shaft','Ліва піввісь'),
    ('Right drive shaft','Права піввісь'),
    ('Torque converter','Гідротрансформатор'),
    ('Front left control arm','Передній лівий ричаг'),
    ('Front right control arm','Передній правий ричаг'),
    ('Front left shock absorber','Передній лівий амортизатор'),
    ('Front right shock absorber','Передній правий амортизатор'),
    ('Rear left shock absorber','Задній лівий амортизатор'),
    ('Rear right shock absorber','Задній правий амортизатор'),
    ('Stabilizer bar','Стабілізатор'),
    ('ABS module','Блок ABS'),
    ('Brake booster','Вакуумний підсилювач гальм'),
    ('Brake master cylinder','Головний гальмівний циліндр'),
    ('Front brake disc','Передній гальмівний диск'),
    ('Rear brake disc','Задній гальмівний диск'),
    ('ABS sensor','Датчик ABS'),
    ('Camshaft sensor','Датчик розподільчого валу'),
    ('Crankshaft sensor','Датчик колінвала'),
    ('Engine ECU','Блок управління двигуном'),
    ('Fuse box','Блок запобіжників'),
    ('Ignition switch','Замок запалювання'),
    ('Parking sensor','Парктронік'),
    ('Center console','Центральна консоль'),
    ('Climate control unit','Блок клімат-контролю'),
    ('Driver airbag','Подушка безпеки водія'),
    ('Glove box','Бардачок'),
    ('Instrument cluster','Панель приладів'),
    ('Seat belt','Ремінь безпеки'),
    ('AC condenser','Радіатор кондиціонера'),
    ('Coolant hose','Патрубок охолодження'),
    ('Expansion tank','Розширювальний бачок'),
    ('Intercooler','Інтеркулер'),
    ('Radiator fan','Вентилятор радіатора'),
    ('Thermostat','Термостат'),
    ('Front left door glass','Переднє ліве скло дверей'),
    ('Front right door glass','Переднє праве скло дверей'),
    ('Rear left door glass','Заднє ліве скло дверей'),
    ('Rear right door glass','Заднє праве скло дверей'),
    ('Rear window','Заднє скло'),
    ('Windshield','Лобове скло')
)
DELETE FROM part_templates pt
USING name_map nm
WHERE pt.name = nm.en_name
  AND EXISTS (
      SELECT 1
      FROM part_templates pt2
      WHERE pt2.vehicle_type = pt.vehicle_type
        AND pt2.category = pt.category
        AND pt2.name = nm.uk_name
  );

UPDATE part_templates pt
SET name = nm.uk_name
FROM name_map nm
WHERE pt.name = nm.en_name
  AND NOT EXISTS (
      SELECT 1
      FROM part_templates pt2
      WHERE pt2.vehicle_type = pt.vehicle_type
        AND pt2.category = pt.category
        AND pt2.name = nm.uk_name
  );

WITH name_map(en_name, uk_name) AS (
    VALUES
    ('Front panel','Передня панель'),('Hood lock','Замок капота'),('Left side skirt','Лівий поріг'),('Right side skirt','Правий поріг'),('Radiator support','Телевізор'),('Roof','Дах'),('Tailgate','Кришка багажника'),('Left fog light','Ліва протитуманна фара'),('Right fog light','Права протитуманна фара'),('Left turn signal','Лівий поворотник'),('Right turn signal','Правий поворотник'),('AC compressor','Компресор кондиціонера'),('Alternator','Генератор'),('Cylinder head','Головка блоку циліндрів'),('EGR valve','Клапан EGR'),('Engine block','Блок двигуна'),('Engine mount','Подушка двигуна'),('Exhaust manifold','Випускний колектор'),('Flywheel','Маховик'),('High-pressure fuel pump','Паливний насос високого тиску'),('Injector','Форсунка'),('Intake manifold','Впускний колектор'),('Starter','Стартер'),('Throttle body','Дросельна заслінка'),('Axle shaft','Піввісь'),('Clutch','Зчеплення'),('Differential','Диференціал'),('Driveshaft','Карданний вал'),('Gear shifter assembly','Механізм перемикання передач'),('Left drive shaft','Ліва піввісь'),('Right drive shaft','Права піввісь'),('Torque converter','Гідротрансформатор'),('Front left control arm','Передній лівий ричаг'),('Front right control arm','Передній правий ричаг'),('Front left shock absorber','Передній лівий амортизатор'),('Front right shock absorber','Передній правий амортизатор'),('Rear left shock absorber','Задній лівий амортизатор'),('Rear right shock absorber','Задній правий амортизатор'),('Stabilizer bar','Стабілізатор'),('ABS module','Блок ABS'),('Brake booster','Вакуумний підсилювач гальм'),('Brake master cylinder','Головний гальмівний циліндр'),('Front brake disc','Передній гальмівний диск'),('Rear brake disc','Задній гальмівний диск'),('ABS sensor','Датчик ABS'),('Camshaft sensor','Датчик розподільчого валу'),('Crankshaft sensor','Датчик колінвала'),('Engine ECU','Блок управління двигуном'),('Fuse box','Блок запобіжників'),('Ignition switch','Замок запалювання'),('Parking sensor','Парктронік'),('Center console','Центральна консоль'),('Climate control unit','Блок клімат-контролю'),('Driver airbag','Подушка безпеки водія'),('Glove box','Бардачок'),('Instrument cluster','Панель приладів'),('Seat belt','Ремінь безпеки'),('AC condenser','Радіатор кондиціонера'),('Coolant hose','Патрубок охолодження'),('Expansion tank','Розширювальний бачок'),('Intercooler','Інтеркулер'),('Radiator fan','Вентилятор радіатора'),('Thermostat','Термостат'),('Front left door glass','Переднє ліве скло дверей'),('Front right door glass','Переднє праве скло дверей'),('Rear left door glass','Заднє ліве скло дверей'),('Rear right door glass','Заднє праве скло дверей'),('Rear window','Заднє скло'),('Windshield','Лобове скло')
)
UPDATE seller_parts sp
SET name = nm.uk_name,
    updated_at = NOW()
FROM name_map nm
WHERE sp.name = nm.en_name
  AND NOT EXISTS (
      SELECT 1
      FROM seller_parts sp2
      WHERE sp2.car_id = sp.car_id
        AND sp2.name = nm.uk_name
  );

DELETE FROM seller_parts sp
USING name_map nm
WHERE sp.name = nm.en_name
  AND EXISTS (
      SELECT 1
      FROM seller_parts sp2
      WHERE sp2.car_id = sp.car_id
        AND sp2.name = nm.uk_name
  );
