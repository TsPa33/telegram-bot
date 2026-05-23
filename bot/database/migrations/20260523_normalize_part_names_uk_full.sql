-- Ensure canonical Ukrainian part template names and previously generated seller part names.

CREATE TEMP TABLE IF NOT EXISTS tmp_part_name_map (
    old_name TEXT PRIMARY KEY,
    new_name TEXT NOT NULL
) ON COMMIT DROP;

INSERT INTO tmp_part_name_map (old_name, new_name)
VALUES
    ('Front panel', 'Передня панель'),
    ('Hood lock', 'Замок капота'),
    ('Left side skirt', 'Лівий поріг'),
    ('Right side skirt', 'Правий поріг'),
    ('Left wheel arch liner', 'Лівий підкрилок'),
    ('Right wheel arch liner', 'Правий підкрилок'),
    ('Radiator support', 'Телевізор'),
    ('Roof', 'Дах'),
    ('Tailgate', 'Кришка багажника'),
    ('Left fog light', 'Ліва протитуманна фара'),
    ('Right fog light', 'Права протитуманна фара'),
    ('Left trunk light', 'Лівий ліхтар багажника'),
    ('Right trunk light', 'Правий ліхтар багажника'),
    ('Left turn signal', 'Лівий поворотник'),
    ('Right turn signal', 'Правий поворотник'),
    ('AC compressor', 'Компресор кондиціонера'),
    ('Alternator', 'Генератор'),
    ('Cylinder head', 'Головка блоку циліндрів'),
    ('EGR valve', 'Клапан EGR'),
    ('Engine block', 'Блок двигуна'),
    ('Engine mount', 'Подушка двигуна'),
    ('Exhaust manifold', 'Випускний колектор'),
    ('Flywheel', 'Маховик'),
    ('High-pressure fuel pump', 'Паливний насос високого тиску'),
    ('Injector', 'Форсунка'),
    ('Intake manifold', 'Впускний колектор'),
    ('Starter', 'Стартер'),
    ('Throttle body', 'Дросельна заслінка'),
    ('Axle shaft', 'Піввісь'),
    ('Clutch', 'Зчеплення'),
    ('Differential', 'Диференціал'),
    ('Driveshaft', 'Карданний вал'),
    ('Gear shifter assembly', 'Механізм перемикання передач'),
    ('Left drive shaft', 'Ліва піввісь'),
    ('Right drive shaft', 'Права піввісь'),
    ('Torque converter', 'Гідротрансформатор'),
    ('Front left control arm', 'Передній лівий важіль'),
    ('Front right control arm', 'Передній правий важіль'),
    ('Front left hub', 'Передня ліва маточина'),
    ('Front right hub', 'Передня права маточина'),
    ('Rear left hub', 'Задня ліва маточина'),
    ('Rear right hub', 'Задня права маточина'),
    ('Front left shock absorber', 'Передній лівий амортизатор'),
    ('Front right shock absorber', 'Передній правий амортизатор'),
    ('Rear left shock absorber', 'Задній лівий амортизатор'),
    ('Rear right shock absorber', 'Задній правий амортизатор'),
    ('Front spring', 'Передня пружина'),
    ('Rear spring', 'Задня пружина'),
    ('Front subframe', 'Передній підрамник'),
    ('Rear subframe', 'Задній підрамник'),
    ('Rear axle beam', 'Задня балка'),
    ('Stabilizer bar', 'Стабілізатор'),
    ('ABS module', 'Блок ABS'),
    ('Brake booster', 'Вакуумний підсилювач гальм'),
    ('Brake master cylinder', 'Головний гальмівний циліндр'),
    ('Front brake disc', 'Передній гальмівний диск'),
    ('Rear brake disc', 'Задній гальмівний диск'),
    ('Front left brake caliper', 'Передній лівий супорт'),
    ('Front right brake caliper', 'Передній правий супорт'),
    ('Rear left brake caliper', 'Задній лівий супорт'),
    ('Rear right brake caliper', 'Задній правий супорт'),
    ('ABS sensor', 'Датчик ABS'),
    ('Camshaft sensor', 'Датчик розподільчого валу'),
    ('Crankshaft sensor', 'Датчик колінвала'),
    ('Comfort control module', 'Блок комфорту'),
    ('Engine ECU', 'Блок управління двигуном'),
    ('Engine wiring harness', 'Проводка двигуна'),
    ('Fuel pressure sensor', 'Датчик тиску палива'),
    ('Fuse box', 'Блок запобіжників'),
    ('Ignition switch', 'Замок запалювання'),
    ('Interior wiring harness', 'Салонна проводка'),
    ('Key', 'Ключ'),
    ('Left window regulator', 'Лівий склопідйомник'),
    ('Right window regulator', 'Правий склопідйомник'),
    ('Parking sensor', 'Парктронік'),
    ('Center console', 'Центральна консоль'),
    ('Climate control unit', 'Блок клімат-контролю'),
    ('Driver airbag', 'Подушка безпеки водія'),
    ('Passenger airbag', 'Подушка безпеки пасажира'),
    ('Glove box', 'Бардачок'),
    ('Instrument cluster', 'Панель приладів'),
    ('Left door card', 'Ліва дверна карта'),
    ('Right door card', 'Права дверна карта'),
    ('Radio unit', 'Магнітола'),
    ('Rear bench seat', 'Задній диван'),
    ('Seat belt', 'Ремінь безпеки'),
    ('AC condenser', 'Радіатор кондиціонера'),
    ('Coolant hose', 'Патрубок охолодження'),
    ('Expansion tank', 'Розширювальний бачок'),
    ('Heater blower motor', 'Моторчик пічки'),
    ('Heater core', 'Радіатор пічки'),
    ('Intercooler', 'Інтеркулер'),
    ('Radiator fan', 'Вентилятор радіатора'),
    ('Thermostat', 'Термостат'),
    ('Front left door glass', 'Переднє ліве скло дверей'),
    ('Front right door glass', 'Переднє праве скло дверей'),
    ('Rear left door glass', 'Заднє ліве скло дверей'),
    ('Rear right door glass', 'Заднє праве скло дверей'),
    ('Rear window', 'Заднє скло'),
    ('Windshield', 'Лобове скло')
ON CONFLICT (old_name) DO UPDATE
SET new_name = EXCLUDED.new_name;

DELETE FROM part_templates pt
USING tmp_part_name_map nm
WHERE pt.name = nm.old_name
  AND EXISTS (
      SELECT 1
      FROM part_templates pt2
      WHERE pt2.vehicle_type = pt.vehicle_type
        AND pt2.category = pt.category
        AND pt2.name = nm.new_name
  );

UPDATE part_templates pt
SET name = nm.new_name
FROM tmp_part_name_map nm
WHERE pt.name = nm.old_name
  AND NOT EXISTS (
      SELECT 1
      FROM part_templates pt2
      WHERE pt2.vehicle_type = pt.vehicle_type
        AND pt2.category = pt.category
        AND pt2.name = nm.new_name
  );

UPDATE seller_parts sp
SET name = nm.new_name,
    updated_at = NOW()
FROM tmp_part_name_map nm
WHERE sp.name = nm.old_name
  AND NOT EXISTS (
      SELECT 1
      FROM seller_parts sp2
      WHERE sp2.car_id = sp.car_id
        AND LOWER(sp2.name) = LOWER(nm.new_name)
        AND sp2.id <> sp.id
  );

UPDATE seller_parts sp
SET description = sp.name || ' з авто. Уточнюйте стан, сумісність та комплектацію.',
    updated_at = NOW()
WHERE COALESCE(NULLIF(TRIM(sp.description), ''), '') = ''
  AND EXISTS (
      SELECT 1
      FROM tmp_part_name_map nm
      WHERE nm.new_name = sp.name
  );
