# Public photo pilot review — 2026-11-26

First isolated CI run 45875916412, SHA 4d31003d: six fixture tests passed; three of four public candidates technically passed. Alfa 147 failed license parsing; the public file page states CC0. This patch adds the cc-zero alias and deed URL canonicalization while keeping exact URL allowlist checks. Actual API values will be logged on next pilot. No approval is inferred from a failed request.

Actual artifact 15144473859 downloaded and visually inspected: Volvo XC90 good cutout; DAF XF faint background near mirror; Audi Q5 weak wheel edges and translucent areas. No asset published. First peak RSS 667.7 MiB. Mask refinement is a pilot heuristic, with new unit checks, not guaranteed visual improvement. CPU memory arena/pattern disabled as an experiment. SHA256 pinned to the downloaded pilot weights. Weight licensing approval remains outstanding. Do not run inference inside the live Warehouse process before independent resource test; separate processor recommended, not deployed.

Previous output: Audi 51044 bytes / 1.218s, DAF 23048 bytes / .958s, Volvo 26150 bytes / .889s. Rerun all four and compare visual quality and peak RSS. Still requires exact model/year review, source credits, full pipeline and staging acceptance. No production, Warehouse stock, OEM, billing, DB changes or Railway deployment.
