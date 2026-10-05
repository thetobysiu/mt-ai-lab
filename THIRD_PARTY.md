# Third-party material

This repository contains material that was not written for this project. Each item keeps
its own licence and attribution.

## 24-floor Magic Tower game data (ckcz123/mota-js)

- **Where:** `data/games/24/project/` (`data.js`, `enemys.js`, `items.js`, `maps.js`, `icons.js`,
  `floors/*.js`, six sprite sheets under `materials/` and `images/`) and the sprite sheets copied
  from it into `mota/dashboard/web/public/sprites/` (with the tile index `mota/dashboard/web/lib/sprites.json`).
- **Source:** the 24-floor sample tower of the HTML5 Magic Tower template, version 2.10.3,
  https://github.com/ckcz123/mota-js
- **Licence:** BSD 3-Clause, reproduced below. The files are unchanged copies.

```
BSD 3-Clause License

Copyright (c) 2018, ckcz123
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

* Redistributions of source code must retain the above copyright notice, this
  list of conditions and the following disclaimer.

* Redistributions in binary form must reproduce the above copyright notice,
  this list of conditions and the following disclaimer in the documentation
  and/or other materials provided with the distribution.

* Neither the name of the copyright holder nor the names of its
  contributors may be used to endorse or promote products derived from
  this software without specific prior written permission.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
```

## Breadth-first solver and test maps (ckcz123/magic-tower-AI)

- **Where:** `tools/java_bfs/*.java` (a modified copy of the published solver: an exact
  dominance test, a summary mode and a batch mode were added), `mota/solver/bfs_solver.py`
  (a Python port of it) and the two test maps `data/floors/simple.txt` and
  `data/floors/complex.txt`.
- **Source:** https://github.com/ckcz123/magic-tower-AI (Java sources under `AI/src`, maps under `test/`).
- **Licence:** the upstream repository does not state a licence. The material is included with
  attribution for the reproduction of the thesis results; all rights to the original code and maps
  remain with their author. If you are the author and want it removed or relicensed, please open an issue.

## Front-end dependencies

The web front end installs its dependencies from npm (`mota/dashboard/web/package-lock.json`);
they are not stored in this repository and carry their own licences (Next.js, React and
Tailwind CSS are MIT-licensed).
