# Third-party notices

Current UTK input compression, tool output compression and response instructions are implemented in this repository. The native runtime does not install, import or launch Headroom, RTK or Caveman.

Historical integration releases referenced:
- Headroom AI, Apache-2.0: https://github.com/chopratejas/headroom
- RTK, Apache-2.0: https://github.com/rtk-ai/rtk
- Caveman skill instructions, MIT: https://github.com/JuliusBrussee/caveman

Historical attributions remain here for provenance. No Caveman BSL engine code is bundled. The current response instructions are authored for UTK.

PyYAML is used to validate managed Hermes configuration before activation and is distributed under the MIT license: https://github.com/yaml/pyyaml

Runtime/build dependencies retain their own licenses: FastAPI (MIT), HTTPX (BSD-3-Clause), Textual (MIT), Typer (MIT), Uvicorn (BSD-3-Clause), Tomli (MIT), React (MIT), Vite (MIT), and their transitive dependencies. Bundled frontend assets retain upstream license comments.
