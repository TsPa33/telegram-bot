-- Normalize generated dismantling templates and auto-generated seller parts to Ukrainian.

UPDATE part_templates
SET category = CASE category
    WHEN 'Body' THEN 'Кузов'
    WHEN 'Optics' THEN 'Оптика'
    WHEN 'Engine' THEN 'Двигун'
    WHEN 'Interior' THEN 'Салон'
    WHEN 'Suspension' THEN 'Підвіска'
    WHEN 'Electrical' THEN 'Електрика'
    WHEN 'Transmission' THEN 'Трансмісія'
    WHEN 'Cooling / AC' THEN 'Охолодження'
    ELSE category
END;

UPDATE part_templates
SET name = CASE name
    WHEN 'Front bumper' THEN 'Передній бампер'
    WHEN 'Rear bumper' THEN 'Задній бампер'
    WHEN 'Front left door' THEN 'Передні ліві двері'
    WHEN 'Front right door' THEN 'Передні праві двері'
    WHEN 'Rear left door' THEN 'Задні ліві двері'
    WHEN 'Rear right door' THEN 'Задні праві двері'
    WHEN 'Hood' THEN 'Капот'
    WHEN 'Trunk' THEN 'Кришка багажника'
    WHEN 'Trunk lid' THEN 'Кришка багажника'
    WHEN 'Fender' THEN 'Крило'
    WHEN 'Front left fender' THEN 'Переднє ліве крило'
    WHEN 'Front right fender' THEN 'Переднє праве крило'
    WHEN 'Headlight' THEN 'Фара'
    WHEN 'Left headlight' THEN 'Ліва фара'
    WHEN 'Right headlight' THEN 'Права фара'
    WHEN 'Taillight' THEN 'Задній ліхтар'
    WHEN 'Left tail light' THEN 'Лівий задній ліхтар'
    WHEN 'Right tail light' THEN 'Правий задній ліхтар'
    WHEN 'Engine' THEN 'Двигун'
    WHEN 'Complete engine' THEN 'Двигун у зборі'
    WHEN 'Transmission' THEN 'КПП'
    WHEN 'Manual gearbox' THEN 'МКПП'
    WHEN 'Automatic gearbox' THEN 'АКПП'
    WHEN 'Turbocharger' THEN 'Турбіна'
    WHEN 'Radiator' THEN 'Радіатор'
    WHEN 'Main radiator' THEN 'Основний радіатор'
    WHEN 'Mirror' THEN 'Дзеркало'
    WHEN 'Left mirror' THEN 'Ліве дзеркало'
    WHEN 'Right mirror' THEN 'Праве дзеркало'
    WHEN 'Steering wheel' THEN 'Кермо'
    WHEN 'Dashboard' THEN 'Торпедо'
    WHEN 'Seat' THEN 'Сидіння'
    WHEN 'Driver seat' THEN 'Сидіння водія'
    WHEN 'Passenger seat' THEN 'Сидіння пасажира'
    WHEN 'Bumper reinforcement' THEN 'Підсилювач бампера'
    ELSE name
END;

UPDATE seller_parts
SET
    category = CASE category
        WHEN 'Body' THEN 'Кузов'
        WHEN 'Optics' THEN 'Оптика'
        WHEN 'Engine' THEN 'Двигун'
        WHEN 'Interior' THEN 'Салон'
        WHEN 'Suspension' THEN 'Підвіска'
        WHEN 'Electrical' THEN 'Електрика'
        WHEN 'Transmission' THEN 'Трансмісія'
        WHEN 'Cooling / AC' THEN 'Охолодження'
        ELSE category
    END,
    name = CASE name
        WHEN 'Front bumper' THEN 'Передній бампер'
        WHEN 'Rear bumper' THEN 'Задній бампер'
        WHEN 'Front left door' THEN 'Передні ліві двері'
        WHEN 'Front right door' THEN 'Передні праві двері'
        WHEN 'Rear left door' THEN 'Задні ліві двері'
        WHEN 'Rear right door' THEN 'Задні праві двері'
        WHEN 'Hood' THEN 'Капот'
        WHEN 'Trunk' THEN 'Кришка багажника'
        WHEN 'Trunk lid' THEN 'Кришка багажника'
        WHEN 'Fender' THEN 'Крило'
        WHEN 'Front left fender' THEN 'Переднє ліве крило'
        WHEN 'Front right fender' THEN 'Переднє праве крило'
        WHEN 'Headlight' THEN 'Фара'
        WHEN 'Left headlight' THEN 'Ліва фара'
        WHEN 'Right headlight' THEN 'Права фара'
        WHEN 'Taillight' THEN 'Задній ліхтар'
        WHEN 'Left tail light' THEN 'Лівий задній ліхтар'
        WHEN 'Right tail light' THEN 'Правий задній ліхтар'
        WHEN 'Engine' THEN 'Двигун'
        WHEN 'Complete engine' THEN 'Двигун у зборі'
        WHEN 'Transmission' THEN 'КПП'
        WHEN 'Manual gearbox' THEN 'МКПП'
        WHEN 'Automatic gearbox' THEN 'АКПП'
        WHEN 'Turbocharger' THEN 'Турбіна'
        WHEN 'Radiator' THEN 'Радіатор'
        WHEN 'Main radiator' THEN 'Основний радіатор'
        WHEN 'Mirror' THEN 'Дзеркало'
        WHEN 'Left mirror' THEN 'Ліве дзеркало'
        WHEN 'Right mirror' THEN 'Праве дзеркало'
        WHEN 'Steering wheel' THEN 'Кермо'
        WHEN 'Dashboard' THEN 'Торпедо'
        WHEN 'Seat' THEN 'Сидіння'
        WHEN 'Driver seat' THEN 'Сидіння водія'
        WHEN 'Passenger seat' THEN 'Сидіння пасажира'
        WHEN 'Bumper reinforcement' THEN 'Підсилювач бампера'
        ELSE name
    END,
    description = CASE
        WHEN template_id IS NOT NULL AND description ILIKE '%Авто розбирається на запчастини%' THEN 'Запчастина з авто. Уточнюйте стан, сумісність та комплектацію.'
        ELSE description
    END,
    updated_at = NOW()
WHERE template_id IS NOT NULL
   OR name IN (
        'Front bumper','Rear bumper','Front left door','Front right door','Rear left door','Rear right door','Hood','Trunk','Trunk lid','Fender','Front left fender','Front right fender','Headlight','Left headlight','Right headlight','Taillight','Left tail light','Right tail light','Engine','Complete engine','Transmission','Manual gearbox','Automatic gearbox','Turbocharger','Radiator','Main radiator','Mirror','Left mirror','Right mirror','Steering wheel','Dashboard','Seat','Driver seat','Passenger seat','Bumper reinforcement'
   );
