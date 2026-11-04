import{a as e,i as t,n,o as r,r as i,s as a,t as o}from"./lit-DHh0pNWb.js";var s={attribute:!0,type:String,converter:r,reflect:!1,hasChanged:e},c=(e=s,t,n)=>{let{kind:r,metadata:i}=n,a=globalThis.litPropertyMetadata.get(i);if(a===void 0&&globalThis.litPropertyMetadata.set(i,a=new Map),r===`setter`&&((e=Object.create(e)).wrapped=!0),a.set(n.name,e),r===`accessor`){let{name:r}=n;return{set(n){let i=t.get.call(this);t.set.call(this,n),this.requestUpdate(r,i,e,!0,n)},init(t){return t!==void 0&&this.C(r,void 0,e,t),t}}}if(r===`setter`){let{name:r}=n;return function(n){let i=this[r];t.call(this,n),this.requestUpdate(r,i,e,!0,n)}}throw Error(`Unsupported decorator location: `+r)};function l(e){return(t,n)=>typeof n==`object`?c(e,t,n):((e,t,n)=>{let r=t.hasOwnProperty(n);return t.constructor.createProperty(n,e),r?Object.getOwnPropertyDescriptor(t,n):void 0})(e,t,n)}function u(e){return l({...e,state:!0,attribute:!1})}var d=(e,t,n)=>(n.configurable=!0,n.enumerable=!0,Reflect.decorate&&typeof t!=`object`&&Object.defineProperty(e,t,n),n),f;function p(e){return(t,n)=>d(t,n,{get(){return(this.renderRoot??(f??=document.createDocumentFragment())).querySelectorAll(e)}})}var m={ATTRIBUTE:1,CHILD:2,PROPERTY:3,BOOLEAN_ATTRIBUTE:4,EVENT:5,ELEMENT:6},h=e=>(...t)=>({_$litDirective$:e,values:t}),g=class{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,t,n){this._$Ct=e,this._$AM=t,this._$Ci=n}_$AS(e,t){return this.update(e,t)}update(e,t){return this.render(...t)}},_=h(class extends g{constructor(e){if(super(e),e.type!==m.ATTRIBUTE||e.name!==`class`||e.strings?.length>2)throw Error("`classMap()` can only be used in the `class` attribute and must be the only part in the attribute.")}render(e){return` `+Object.keys(e).filter(t=>e[t]).join(` `)+` `}update(e,[t]){if(this.st===void 0){this.st=new Set,e.strings!==void 0&&(this.nt=new Set(e.strings.join(` `).split(/\s/).filter(e=>e!==``)));for(let e in t)t[e]&&!this.nt?.has(e)&&this.st.add(e);return this.render(t)}let n=e.element.classList;for(let e of this.st)e in t||(n.remove(e),this.st.delete(e));for(let e in t){let r=!!t[e];r===this.st.has(e)||this.nt?.has(e)||(r?(n.add(e),this.st.add(e)):(n.remove(e),this.st.delete(e)))}return i}});function*v(e,t){if(e!==void 0){let n=0;for(let r of e)yield t(r,n++)}}function y(e,t,n){return e?t(e):n?.(e)}var b=Object.defineProperty,x=Object.getOwnPropertyDescriptor,S=(e,t,n,r)=>{for(var i=r>1?void 0:r?x(t,n):t,a=e.length-1,o;a>=0;a--)(o=e[a])&&(i=(r?o(t,n,i):o(i))||i);return r&&i&&b(t,n,i),i};function C(e){return e instanceof RegExp}function w(e){return e===null?`null`:Array.isArray(e)?`array`:e.constructor.name.toLowerCase()}function T(e){return e!==Object(e)}function E(e,{nodeCount:t=3,maxLength:n=15}={}){let r=Array.isArray(e),i=Object.keys(e),a=i.slice(0,t),o=[],s=e=>{switch(w(e)){case`object`:return Object.keys(e).length===0?`{ }`:`{ ... }`;case`array`:return e.length===0?`[ ]`:`[ ... ]`;case`string`:return`"${e.substring(0,n)}${e.length>n?`...`:``}"`;default:return String(e)}},c=[];for(let t of a){let n=[],i=e[t];r||n.push(`${t}: `),n.push(s(i)),c.push(n.join(``))}i.length>t&&c.push(`...`),o.push(c.join(`, `));let l=o.join(``);return r?`[ ${l} ]`:`{ ${l} }`}function*D(e){let t=[[e,``,[]]];for(;t.length;){let[e,n,r]=t.shift();if(n&&(yield[e,n,r]),!T(e))for(let[i,a]of Object.entries(e))t.push([a,`${n}${n?`.`:``}${i}`,[...r,n]])}}function O(e,t){let n=e.split(`.`),r=t.split(`.`),i=e=>e===`*`,a=e=>e===`**`,o=0,s=0;for(;o<n.length;){let e=r[s];if(e===n[o]||i(e))s++,o++;else if(a(e))s++,o=n.length-(r.length-s);else return!1}return s===r.length}var k={fromAttribute:e=>e&&e.trim()?JSON.parse(e):void 0,toAttribute:e=>JSON.stringify(e)},A=e=>e!==void 0,j=(e,t)=>C(t)?!!e.match(t):O(e,t),M=(e,t)=>t.split(`.`).reduce((e,t)=>e[t],e),N=(e,t)=>n=>({expanded:{...n.expanded,[e]:A(t)?!!t:!n.expanded[e]}}),P=(e,t)=>(n,r)=>{let i={};if(e)for(let[,n,a]of D(r.data))j(n,e)&&(i[n]=t,a.forEach(e=>i[e]=t));return{expanded:i}},F=e=>(t,n)=>{let r={};if(e)for(let[,t,i]of D(n.data))j(t,e)?(r[t]=!1,i.forEach(e=>r[e]=!1)):r[t]=!0;return{filtered:r}},I=()=>()=>({filtered:{}}),L=e=>()=>({highlight:e}),R=a`
    :where(:host) {
        --background-color: #2a2f3a;
        --color: #f8f8f2;
        --string-color: #a3eea0;
        --number-color: #d19a66;
        --boolean-color: #4ba7ef;
        --null-color: #df9cf3;
        --property-color: #6fb3d2;
        --preview-color: rgba(222, 175, 143, 0.9);
        --highlight-color:  #c92a2a;
        --outline-color: #e0e4e5;
        --outline-width: 1px;
        --outline-style: dotted;

        --font-family: Nimbus Mono PS, Courier New, monospace;
        --font-size: 1rem;
        --line-height: 1.2rem;

        --indent-size: 0.5rem;
        --indentguide-size: 1px;
        --indentguide-style: solid;
        --indentguide-color: #495057;
        --indentguide-color-active: #ced4da;
        --indentguide: var(--indentguide-size) var(--indentguide-style) var(--indentguide-color);
        --indentguide-active: var(--indentguide-size) var(--indentguide-style) var(--indentguide-color-active);
    }

    :host {
        display: block;
        background-color: var(--background-color);
        color: var(--color);
        font-family: var(--font-family);
        font-size: var(--font-size);
        line-height: var(--line-height);
    }

    :focus {
        outline-color: var(--outline-color);
        outline-width: var(--outline-width);
        outline-style: var(--outline-style);
    }

    .preview {
        color: var(--preview-color);
    }

    .null {
        color: var(--null-color);
    }

    .key {
        color: var(--property-color);
        display: inline-flex;
        align-items: flex-start;
    }

    .collapsable::before {
        display: inline-flex;
        font-size: 0.8em;
        content: '▶';
        width: var(--line-height);
        height: var(--line-height);
        align-items: center;
        justify-content: center;

        transition: transform 195ms ease-out;
        transform: rotate(90deg);

        color: inherit;
    }

    .collapsable--collapsed::before {
        transform: rotate(0);
    }

    .collapsable {
        cursor: pointer;
        user-select: none;
    }

    .string {
        color: var(--string-color);
    }

    .number {
        color: var(--number-color);
    }

    .boolean {
        color: var(--boolean-color);
    }

    ul {
        padding: 0;
        clear: both;
    }

    ul,
    li {
        list-style: none;
        position: relative;
    }

    li ul > li {
        position: relative;
        margin-left: calc(var(--indent-size) + var(--line-height));
        padding-left: 0px;
    }

    ul ul::before {
        content: '';
        border-left: var(--indentguide);
        position: absolute;
        left: calc(var(--line-height) / 2 - var(--indentguide-size));
        top: 0.2rem;
        bottom: 0.2rem;
    }

    ul ul:hover::before {
        border-left: var(--indentguide-active);
    }

    mark {
        background-color: var(--highlight-color);
    }
`,z=class extends o{constructor(){super(),this.state={expanded:{},filtered:{},highlight:null},this.lastFocusedItem=null,this.#e=e=>t=>{t.preventDefault(),this.setState(N(e))},this.#t=e=>{let t=e.target;e.target===this&&this.#i(this.lastFocusedItem||this.nodeElements[0]),t.matches(`[role="treeitem"]`)&&(this.lastFocusedItem&&(this.lastFocusedItem.tabIndex=-1),this.lastFocusedItem=t,this.tabIndex=-1,t.tabIndex=0)},this.#n=e=>{let t=e.relatedTarget;(!t||!this.contains(t))&&(this.tabIndex=0)},this.addEventListener(`focusin`,this.#t),this.addEventListener(`focusout`,this.#n)}static{this.styles=[R]}static customRenderer(e,t){return JSON.stringify(e)}async setState(e){let t=this.state;this.state={...t,...e(t,this)}}connectedCallback(){!this.hasAttribute(`data`)&&!A(this.data)&&this.setAttribute(`data`,this.innerText),this.setAttribute(`role`,`node`),this.setAttribute(`tabindex`,`0`),super.connectedCallback()}#e;#t;#n;#r(e){if(![`ArrowDown`,`ArrowUp`,`ArrowRight`,`ArrowLeft`,`Home`,`End`].includes(e.key))return;let t=[...this.nodeElements],n=this.matches(`:dir(ltr)`),r=this.matches(`:dir(rtl)`);if(t.length>0){e.preventDefault();let i=t.findIndex(e=>e.matches(`:focus`)),a=t[i],o=this.state.expanded[a.dataset.path],s=T(M(this.data,a.dataset.path)),c=e=>{let n=t[Math.max(Math.min(e,t.length-1),0)];this.#i(n)},l=e=>{this.setState(N(a.dataset.path,e))};e.key===`ArrowDown`?c(i+1):e.key===`ArrowUp`?c(i-1):n&&e.key===`ArrowRight`||r&&e.key===`ArrowLeft`?!a||o||s?c(i+1):l(!0):n&&e.key===`ArrowLeft`||r&&e.key===`ArrowRight`?!a||!o||s?c(i-1):l(!1):e.key===`Home`?c(0):e.key===`End`&&c(t.length-1)}}#i(e){e.focus()}expand(e){this.setState(P(e,!0))}expandAll(){this.setState(P(`**`,!0))}collapseAll(){this.setState(P(`**`,!1))}collapse(e){this.setState(P(e,!1))}*search(e){for(let[t,n]of D(this.data))T(t)&&String(t).match(e)&&(this.expand(n),this.updateComplete.then(()=>{let e=this.shadowRoot.querySelector(`[data-path="${n}"]`);e.scrollIntoView({behavior:`smooth`,inline:`center`,block:`center`}),e.focus()}),this.setState(L(n)),yield{value:t,path:n});this.setState(L(null))}filter(e){this.setState(F(e))}resetFilter(){this.setState(I())}renderObject(e,r){return t`
            <ul part="object" role="group">
                ${v(Object.entries(e),([e,i])=>{let a=r?`${r}.${e}`:e,o=T(i),s=this.state.expanded[a];return this.state.filtered[a]?n:t`
                              <li
                                  part="property"
                                  role="treeitem"
                                  data-path="${a}"
                                  aria-expanded="${s?`true`:`false`}"
                                  tabindex="-1"
                                  .hidden="${this.state.filtered[a]}"
                                  aria-hidden="${this.state.filtered[a]}"
                              >
                                  <span
                                      part="key"
                                      class="${_({key:e,collapsable:!o,"collapsable--collapsed":!this.state.expanded[a]})}"
                                      @click="${o?null:this.#e(a)}"
                                  >
                                      ${e}:
                                      ${y(!o&&!s,()=>this.renderNodePreview(i))}
                                  </span>

                                  ${y(o||s,()=>this.renderValue(i,a))}
                              </li>
                          `})}
            </ul>
        `}renderValue(e,t=``){return T(e)?this.renderPrimitive(e,t):this.renderObject(e,t)}renderNodePreview(e){return t`<span part="preview" class="preview"> ${E(e)} </span>`}renderPrimitive(e,n){let r=this.state.highlight,i=w(e),a=this.constructor.customRenderer(e,n),o=t`
            <span part="primitive primitive-${i}" class="${w(e)}"> ${a} </span>
        `;return n===r?t`<mark part="highlight">${o}</mark>`:o}render(){let e=this.data;return t`
            <div
                part="base"
                @keydown=${this.#r}
                @focusin="${this.#t}"
                @focusout="${this.#n}"
            >
                ${y(A(e),()=>this.renderValue(e))}
            </div>
        `}};S([l({converter:k,type:Object})],z.prototype,`data`,2),S([u()],z.prototype,`state`,2),S([u()],z.prototype,`lastFocusedItem`,2),S([p(`[role="treeitem"]`)],z.prototype,`nodeElements`,2),customElements.define(`json-viewer`,z);