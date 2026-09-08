// Matching visible frame-code v1 decoder. CRC is corruption detection, not auth.
export const markerWidth = 352, markerHeight = 12;

export function decodePixels(pixels: Uint8ClampedArray) {
  if (pixels.length !== markerWidth*markerHeight*4) return null;
  const bytes = new Uint8Array(11);
  for (let bit=0; bit<88; bit++) {
    let sum=0;
    for(let y=4;y<8;y++)for(let x=1;x<=2;x++) {
      const p=(y*markerWidth+bit*4+x)*4;
      sum+=(pixels[p]+pixels[p+1]+pixels[p+2])/3;
    }
    const level=sum/8;
    if(level>70 && level<180)return null;
    bytes[Math.floor(bit/8)] |= Number(level>=180) << (7-bit%8);
  }
  let crc=0xffff;
  for(const byte of bytes.slice(0,9)) {
    crc ^= byte<<8;
    for(let bit=0;bit<8;bit++)crc=((crc&0x8000)?(crc<<1)^0x1021:crc<<1)&0xffff;
  }
  if(bytes[0]!==0xc1 || bytes[1]!==1 || ![97,98,99].includes(bytes[6]) || crc!==((bytes[9]<<8)|bytes[10]))return null;
  const hex=Array.from(bytes, byte=>byte.toString(16).padStart(2,"0")).join("");
  return {packet_hex:hex,source_tag:hex.slice(4,12),camera:String.fromCharCode(bytes[6]),frame:(bytes[7]<<8)|bytes[8]};
}

export function readFrameCode(video: HTMLVideoElement, context: CanvasRenderingContext2D) {
  if(video.videoWidth!==960 || video.videoHeight!==540 || video.readyState<2 || video.paused)return null;
  context.drawImage(video, 600,520,markerWidth,markerHeight,0,0,markerWidth,markerHeight);
  return decodePixels(context.getImageData(0,0,markerWidth,markerHeight).data);
}
