import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './index.module.css';

const featureLinks = [
  {
    label: 'Start here',
    title: 'Set up a school',
    text: 'Install Shelf-School, create the administrator, configure the library, and add the first borrowers.',
    to: '/docs/getting-started/quickstart',
  },
  {
    label: 'Daily workflow',
    title: 'Borrow and return',
    text: 'Run the public circulation kiosk without student accounts or library cards.',
    to: '/docs/usage/self-service',
  },
  {
    label: 'Catalog',
    title: 'Add books by photo',
    text: 'Decode ISBN barcodes locally, retrieve free metadata, and create physical copy labels.',
    to: '/docs/usage/photo-intake',
  },
  {
    label: 'Operate',
    title: 'Protect school data',
    text: 'Understand SQLite backups, local media, troubleshooting, and safe maintenance.',
    to: '/docs/operations/backup',
  },
];

export default function Home() {
  const heroImage = useBaseUrl('/img/circulation-desk.png');

  return (
    <Layout
      title="Shelf-School"
      description="Open-source circulation and cataloging for small school libraries">
      <main className={styles.page}>
        <section className={styles.hero} style={{backgroundImage: `url(${heroImage})`}}>
          <div className={styles.heroContent}>
            <p className={styles.kicker}>Open-source school library software</p>
            <h1>Shelf-School</h1>
            <p className={styles.lede}>
              Public self-checkout with book photos, simple cataloging, and
              staff controls for small school libraries.
            </p>
            <div className={styles.actions}>
              <Link className="button button--primary button--lg" to="/docs/overview">
                Read the docs
              </Link>
              <Link className="button button--secondary button--lg" to="/docs/getting-started/quickstart">
                Quick start
              </Link>
            </div>
          </div>
        </section>

        <section className={styles.sections} aria-label="Documentation sections">
          <div className={styles.grid}>
            {featureLinks.map((feature) => (
              <Link className={styles.card} to={feature.to} key={feature.title}>
                <span>{feature.label}</span>
                <h2>{feature.title}</h2>
                <p>{feature.text}</p>
              </Link>
            ))}
          </div>
        </section>
      </main>
    </Layout>
  );
}
