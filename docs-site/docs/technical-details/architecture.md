# Architecture

Shelf-School is a server-rendered Django application designed to keep a school
library operational on one computer. The same Mac can serve its own kiosk or a
small set of circulation devices on trusted school Wi-Fi.

## Deployment topology

<div className="architecture-map" role="img" aria-label="Circulation and staff devices connect over trusted school Wi-Fi to Shelf-School on a dedicated Mac. Django uses local SQLite and media storage and optionally requests metadata from Open Library.">
  <div className="architecture-clients">
    <div className="architecture-node architecture-node-public">
      <span className="architecture-kicker">Public surface</span>
      <strong>Circulation devices</strong>
      <small>Borrower search, book photo, manual selection, and confirmation</small>
    </div>
    <div className="architecture-node architecture-node-staff">
      <span className="architecture-kicker">Authenticated surface</span>
      <strong>Staff browser</strong>
      <small>Catalog, borrowers, reports, settings, and backups</small>
    </div>
  </div>

  <div className="architecture-route">
    <span aria-hidden="true"></span>
    <small>Trusted Wi-Fi or this Mac &middot; HTTP port 8427</small>
  </div>

  <div className="architecture-host">
    <div className="architecture-host-heading">
      <span>Dedicated Mac</span>
      <strong>Shelf-School</strong>
    </div>
    <div className="architecture-services">
      <div><strong>Django views</strong><small>HTML, forms, authentication, and validation</small></div>
      <div><strong>Domain rules</strong><small>Copies, borrowers, loans, and signed confirmation</small></div>
      <div><strong>Local decoder</strong><small><code>zxing-cpp</code> reads QR and ISBN barcodes</small></div>
    </div>
  </div>

  <div className="architecture-route">
    <span aria-hidden="true"></span>
    <small>Local filesystem by default</small>
  </div>

  <div className="architecture-storage">
    <div className="architecture-node architecture-node-data">
      <span className="architecture-kicker">Structured data</span>
      <strong>SQLite</strong>
      <small>Books, copies, people, settings, and loan history</small>
    </div>
    <div className="architecture-node architecture-node-media">
      <span className="architecture-kicker">Stored files</span>
      <strong>Media directory</strong>
      <small>School branding and intentional catalog covers</small>
    </div>
    <div className="architecture-node architecture-node-external">
      <span className="architecture-kicker">Optional outbound request</span>
      <strong>Open Library</strong>
      <small>Free ISBN metadata and available cover images</small>
    </div>
  </div>
</div>

The Mac is the system of record. Circulation devices do not keep a second copy
of the catalog, and ISBN-intake or circulation photos are not retained after
decoding.

## Circulation write path

<div className="architecture-flow" role="img" aria-label="A five-step circulation flow identifies the borrower, identifies the physical copy, validates library rules, presents confirmation, and commits an atomic loan update.">
  <div className="architecture-step">
    <span>1</span>
    <strong>Identify borrower</strong>
    <small>Borrower ID or name</small>
  </div>
  <i className="architecture-arrow" aria-hidden="true"></i>
  <div className="architecture-step">
    <span>2</span>
    <strong>Identify copy</strong>
    <small>Photo, QR, ISBN, or manual search</small>
  </div>
  <i className="architecture-arrow" aria-hidden="true"></i>
  <div className="architecture-step">
    <span>3</span>
    <strong>Validate rules</strong>
    <small>Availability, active loan, and ambiguity</small>
  </div>
  <i className="architecture-arrow" aria-hidden="true"></i>
  <div className="architecture-step">
    <span>4</span>
    <strong>Confirm</strong>
    <small>Signed, short-lived transaction token</small>
  </div>
  <i className="architecture-arrow" aria-hidden="true"></i>
  <div className="architecture-step architecture-step-final">
    <span>5</span>
    <strong>Commit loan</strong>
    <small>Locked and revalidated database update</small>
  </div>
</div>

Photo identification never changes circulation state by itself. The final
request locks and revalidates each selected copy inside one database
transaction. **A stale, repeated, or partially invalid multi-book operation
cannot leave half a basket checked out.**

## Domain model

<div className="model-map" role="img" aria-label="A book has many physical copies. A copy has loan history. Every loan belongs to one borrower. A staff account has one synchronized borrower profile.">
  <div className="model-node"><strong>Book</strong><small>Title or edition</small></div>
  <div className="model-relation"><strong>1 to many</strong><small>physical items</small></div>
  <div className="model-node"><strong>Copy</strong><small>Unique QR and status</small></div>
  <div className="model-relation"><strong>1 to many</strong><small>loan history</small></div>
  <div className="model-node"><strong>Loan</strong><small>Checkout, due, return</small></div>
  <div className="model-relation"><strong>many to 1</strong><small>assigned to</small></div>
  <div className="model-node"><strong>Borrower</strong><small>Student or employee</small></div>
</div>

<div className="model-supporting">
  <div><strong>Staff account <span>1 to 1</span> Borrower</strong><small>Borrower ID, name, and email stay synchronized.</small></div>
  <div><strong>School profile <span>1 per installation</span></strong><small>Branding, contact details, and default loan duration.</small></div>
  <div><strong>School class <span>1 to many</span> Students</strong><small>Optional assignment; renaming updates every linked profile.</small></div>
  <div><strong>Employee position <span>1 to many</span> Employees</strong><small>Optional assignment, independent of login permissions.</small></div>
</div>

The database enforces **one active loan per physical copy**. Returned loans stay
as history, and deleting or deactivating staff access does not remove the linked
borrower or circulation records.

Classes and positions are protected foreign keys: assigned entries cannot be
deleted. Deactivation prevents new assignments while preserving existing ones.
The single borrower CSV importer validates both roles and their assignments in
one transaction; it never creates authentication accounts.

## Trust boundaries

<div className="trust-boundaries">
  <div><span>Public</span><strong>Circulation desk</strong><small>Supervised checkout and return without a student login</small></div>
  <div><span>Staff</span><strong>Library operations</strong><small>Catalog, borrowers, reports, backups, and school settings</small></div>
  <div><span>System administrator</span><strong>Advanced Django Admin</strong><small>Exceptional technical database and permission maintenance</small></div>
</div>

Named recent activity is not rendered for signed-out users. The public desk is
intentionally reachable on the trusted school network; staff and advanced
surfaces remain protected by Django authentication.

## Storage and external services

- `db.sqlite3` is the default structured store and must be backed up with
  `media/`.
- Uploaded files use local media storage on the dedicated Mac.
- `zxing-cpp` decodes QR and ISBN barcodes locally without a paid API.
- Open Library is contacted only for optional ISBN metadata and covers.
- No paid AI service is required.
