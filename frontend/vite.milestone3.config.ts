// Loopback-only rehearsal; does not change the ordinary development configuration.
import {defineConfig,mergeConfig} from 'vite';
import base from './vite.config.ts';
export default defineConfig(mergeConfig(base,{server:{host:'127.0.0.1',port:5190,strictPort:true,
  proxy:{'/api':{target:'http://127.0.0.1:8022',ws:true}}}}));
