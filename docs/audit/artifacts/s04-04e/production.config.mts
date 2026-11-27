import base from '../../../../.worktrees/gabfin-s01/playwright.config.ts';
import {fileURLToPath} from 'node:url';
const root=fileURLToPath(new URL('../../../../.worktrees/gabfin-s01/',import.meta.url));
export default {...base,testDir:root+'tests/e2e',testMatch:['acceptance.spec.ts'],
  outputDir:fileURLToPath(new URL('./production-results/',import.meta.url)),
  use:{...base.use,baseURL:'http://127.0.0.1:19046'},
  webServer:{...base.webServer,cwd:root,command:'npm.cmd --prefix apps/desk-web run preview -- --port 19046 --strictPort',url:'http://127.0.0.1:19046',reuseExistingServer:false}};
