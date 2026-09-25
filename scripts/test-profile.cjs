// Isolate automated UI checks from the user's running desktop session.
const {app} = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const name = process.env.VIDEO_SHEET_TEST_PROFILE === 'playback' ? 'playback' : 'desktop';
const profile = path.join(__dirname, '..', 'diagnostics', `${name}-test-profile`);
fs.mkdirSync(profile, {recursive:true});
app.setPath('userData', profile);
