import { StringDecoder } from "node:string_decoder";

export class Utf8StreamDecoder {
  private readonly decoder = new StringDecoder("utf8");

  write(chunk: Buffer): string {
    return this.decoder.write(chunk);
  }

  end(chunk?: Buffer): string {
    return this.decoder.end(chunk);
  }
}

export function createUtf8WorkerEnv(base: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  return {
    ...base,
    PYTHONUTF8: "1",
    PYTHONIOENCODING: "utf-8",
  };
}
