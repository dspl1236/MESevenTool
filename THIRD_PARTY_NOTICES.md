# Third-Party Notices

MESevenTool includes code derived from the projects below. Their licenses apply
to the derived portions as indicated.

## lsdlsd88/TCU-FRF-SGO-UNPACKER (MIT)

`meseventool/sgo.py` — the SGML Object File (SGO) container parser and the
legacy flash-decode primitives (`record_decode`, `lfsr_decode`, `deinterleave`,
`bitrev32`) — is a faithful port of `sgo_unpack.py` and `sgo_legacy.py` from:

> <https://github.com/lsdlsd88/TCU-FRF-SGO-UNPACKER>

That project is published under the MIT License. `sgo_legacy.py` is itself
verified against the original `SGO Extract.exe` (2013) with the Unicorn CPU
emulator, and the container parser derives from calledit's
`SGML_Object_File_reader` (`read_sgo.php`).

The `motronic7` descramble word `GEHEIM` reproduced in `meseventool/sgo.py` is
interoperability material published in that MIT project. It is a container
decode key only — not immobiliser, component-protection, or signature material.

```
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
