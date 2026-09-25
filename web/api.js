// All platform access lives here; the interface itself uses only web APIs.
export class WorkspaceAPI {
  constructor() {
    this.token = location.hash.slice(1) || sessionStorage.getItem('drum-session') || '';
    if (this.token) sessionStorage.setItem('drum-session', this.token);
    history.replaceState(null, '', location.pathname);
  }
  url(path, values = {}) {
    return `/api/${path}?${new URLSearchParams({token: this.token, ...values})}`;
  }
  async request(path, options = {}) {
    const response = await fetch(`/api/${path}`, {
      ...options, headers: {'X-Session-Token': this.token, ...options.headers},
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'The operation could not be completed.');
    return result;
  }
  state() { return this.request('state'); }
  command(action, values = {}) {
    return this.request('command', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({action, ...values})});
  }
  upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
      xhr.setRequestHeader('X-Session-Token', this.token);
      xhr.setRequestHeader('X-Filename', encodeURIComponent(file.name));
      xhr.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.onerror = () => reject(new Error('Upload interrupted. Please try again.'));
      xhr.onload = () => {
        try {
          const result = JSON.parse(xhr.responseText);
          if (xhr.status !== 200) reject(new Error(result.error)); else resolve(result.path);
        } catch { reject(new Error('Could not upload the file.')); }
      };
      xhr.send(file);
    });
  }
  async choose(kind) {
    return window.desktop?.chooseFile(kind) ?? null;
  }
  download(id, name) {
    const link = document.createElement('a');
    link.href = this.url('download', {id});
    link.download = name;
    document.body.append(link);
    link.click();
    link.remove();
  }
}
