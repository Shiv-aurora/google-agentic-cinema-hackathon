import pytest
import json
import subprocess

from services.media.framecode import CELL, HEIGHT, WIDTH, decode_strip, packet, strip


def test_frame_code_roundtrip_and_camera_identity():
    for camera in "abc":
        for frame in (0, 1, 29, 30, 1799, 65535):
            assert decode_strip(strip("a1b2c3d4", camera, frame)) == {"source_tag": "a1b2c3d4", "camera": camera, "frame": frame}


def test_crc_and_contrast_fail_closed():
    original = strip("a1b2c3d4", "b", 39)
    for bit in range(88):
        damaged = bytearray(original)
        for y in range(HEIGHT):
            for x in range(CELL):
                pos = y*WIDTH+bit*CELL+x
                damaged[pos] = 251-damaged[pos]
        assert decode_strip(damaged) is None
    assert decode_strip(bytes([127])*(WIDTH*HEIGHT)) is None
    assert decode_strip(original[:-1]) is None
    with pytest.raises(ValueError):
        packet("a1b2c3d4", "d", 1)


def test_browser_decoder_matches_python_packets():
    code = """import {readFileSync} from 'node:fs';
import {transformSync} from 'esbuild';
const compiled=transformSync(readFileSync('apps/web/framecode.ts','utf8'),{loader:'ts',format:'esm'}).code;
const {decodePixels}=await import('data:text/javascript;base64,'+Buffer.from(compiled).toString('base64'));
const inputs=JSON.parse(readFileSync(0,'utf8'));
console.log(JSON.stringify(inputs.map(gray=>{
  const rgba=new Uint8ClampedArray(gray.length*4);
  gray.forEach((value,index)=>rgba.set([value,value,value,255],index*4));
  return decodePixels(rgba);
})));"""
    inputs = [list(strip("a1b2c3d4", "c", 1799)), [127]*(WIDTH*HEIGHT)]
    result = subprocess.run(["node", "--input-type=module", "-e", code],
        input=json.dumps(inputs), capture_output=True, text=True, check=True, timeout=10)
    decoded = json.loads(result.stdout)
    assert decoded[0] == {"source_tag":"a1b2c3d4", "camera":"c", "frame":1799,
                          "packet_hex":packet("a1b2c3d4", "c", 1799).hex()}
    assert decoded[1] is None
