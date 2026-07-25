import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App';
import { I18nProvider } from './i18n/I18nProvider';
import './styles/tokens.css';
import './styles/base.css';
import './styles/app-shell.css';

const root = document.getElementById('root');
if (!root) throw new Error('SafeSpare: #root is missing from index.html');

ReactDOM.createRoot(root).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
);
