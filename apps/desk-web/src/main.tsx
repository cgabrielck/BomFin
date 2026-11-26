import { createRoot } from 'react-dom/client';
import { Providers } from './app/providers';
import App from './app/App';
import './app/styles.css';

createRoot(document.getElementById('root')!).render(
  <Providers>
    <App />
  </Providers>,
);
