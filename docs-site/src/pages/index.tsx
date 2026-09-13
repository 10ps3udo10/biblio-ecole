import Link from '@docusaurus/Link';
import Layout from '@theme/Layout';
import useBaseUrl from '@docusaurus/useBaseUrl';
import styles from './index.module.css';

const featureLinks = [
  {
    label: 'Start here',
    title: 'Set up a school',
    text: 'Install Shelf-School, create the first staff account, configure the library, and add the first borrowers.',
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
  const logo = useBaseUrl('/img/shelf-school-logo.svg');
  const libraryIllustration = useBaseUrl('/img/montessori-library.svg');
  const circulationImage = useBaseUrl('/img/circulation-desk.png');

  return (
    <Layout
      title="Shelf-School"
      description="Open-source circulation and cataloging for school libraries">
      <main className={styles.page}>
        <section className={styles.intro}>
          <div className={styles.introContent}>
            <img className={styles.productLogo} src={logo} alt="" />
            <p className={styles.kicker}>Open-source school library software</p>
            <h1>Shelf-School</h1>
            <p className={styles.lede}>
              A focused circulation and cataloging system built around how
              students and school employees actually use a library.
            </p>
            <div className={styles.actions}>
              <Link className="button button--primary button--lg" to="/docs/overview">
                User guide
              </Link>
              <Link className="button button--secondary button--lg" to="/docs/getting-started/quickstart">
                Quick start
              </Link>
            </div>
            <div className={styles.principles} aria-label="Product principles">
              <span>No student accounts</span>
              <span>Self-hosted</span>
              <span>No paid AI required</span>
            </div>
            <img
              className={styles.libraryIllustration}
              src={libraryIllustration}
              alt="Montessori library with accessible shelves and children reading"
            />
          </div>
        </section>

        <section className={styles.sections} aria-label="Documentation sections">
          <header className={styles.sectionHeading}>
            <p className={styles.kicker}>Documentation</p>
            <h2>Find the right guide</h2>
            <p>Start with daily library work or go directly to setup and operations.</p>
          </header>
          <div className={styles.grid}>
            {featureLinks.map((feature) => (
              <Link className={styles.card} to={feature.to} key={feature.title}>
                <span>{feature.label}</span>
                <h2>{feature.title}</h2>
                <p>{feature.text}</p>
                <strong aria-hidden="true">View guide →</strong>
              </Link>
            ))}
          </div>
        </section>

        <section className={styles.productView} aria-labelledby="product-view-title">
          <div className={styles.productViewInner}>
            <header className={styles.sectionHeading}>
              <p className={styles.kicker}>Designed for daily use</p>
              <h2 id="product-view-title">A circulation desk students can understand</h2>
              <p>Borrower, book, and confirmation stay visible as one clear workflow.</p>
            </header>
            <img
              className={styles.productImage}
              src={circulationImage}
              alt="Shelf-School public circulation desk showing checkout, borrower search, and three workflow steps"
            />
          </div>
        </section>
      </main>
    </Layout>
  );
}
