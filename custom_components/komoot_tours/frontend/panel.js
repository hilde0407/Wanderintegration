// Seitenleisten-Panel: bettet die Komoot-Oberflaeche (index.html) als iframe ein.
class KomootToursPanel extends HTMLElement {
  set hass(hass) { this._hass = hass; if (this._menu) this._menu.hass = hass; }
  set narrow(narrow) { this._narrow = narrow; if (this._menu) this._menu.narrow = narrow; this._bar && (this._bar.style.display = narrow ? 'flex' : 'none'); }
  set panel(panel) { this._panel = panel; this._render(); }
  connectedCallback() { this._render(); }
  _render() {
    if (this._frame || !this._panel) return;
    const root = this.attachShadow ? (this.shadowRoot || this.attachShadow({ mode: 'open' })) : this;
    root.innerHTML = `<style>
      :host { display: flex; flex-direction: column; height: 100%; background: var(--primary-background-color); }
      .bar { display: none; align-items: center; height: 56px; padding: 0 4px; flex: none; background: var(--app-header-background-color, var(--primary-color)); color: var(--app-header-text-color, #fff); }
      .bar span { font-size: 20px; margin-left: 4px; }
      iframe { flex: 1; width: 100%; border: 0; display: block; }
    </style>
    <div class="bar"><ha-menu-button></ha-menu-button><span>Komoot</span></div>
    <iframe title="Komoot"></iframe>`;
    this._bar = root.querySelector('.bar');
    this._menu = root.querySelector('ha-menu-button');
    this._frame = root.querySelector('iframe');
    if (this._hass) this._menu.hass = this._hass;
    this._menu.narrow = !!this._narrow;
    this._bar.style.display = this._narrow ? 'flex' : 'none';
    this._frame.src = (this._panel.config || {}).page || '/komoot_tours_static/index.html';
  }
}
customElements.define('komoot-tours-panel', KomootToursPanel);
