import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="wrap section">
      <p className="eyebrow">404</p>
      <h1 className="display-3">That page does not exist</h1>
      <p className="lede">The link may be out of date.</p>
      <Link className="btn btn--primary" to="/">Back to start</Link>
    </div>
  );
}
