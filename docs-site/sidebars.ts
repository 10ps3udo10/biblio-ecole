import type {SidebarsConfig} from '@docusaurus/plugin-content-docs';

const sidebars: SidebarsConfig = {
  userGuide: [
    {type: 'doc', id: 'overview', label: 'Overview'},
    {
      type: 'category',
      label: 'Getting Started',
      items: [
        {type: 'doc', id: 'getting-started/quickstart', label: 'Quick Start'},
        {type: 'doc', id: 'getting-started/school-setup', label: 'School Setup'},
      ],
    },
    {
      type: 'category',
      label: 'Daily Use',
      items: [
        {type: 'doc', id: 'usage/self-service', label: 'Self-Service Circulation'},
        {type: 'doc', id: 'usage/photo-intake', label: 'Photo Intake'},
        {type: 'doc', id: 'usage/catalog-import', label: 'Catalog Import'},
        {type: 'doc', id: 'usage/borrowers', label: 'Borrowers'},
        {type: 'doc', id: 'usage/staff-accounts', label: 'Staff Accounts'},
        {type: 'doc', id: 'usage/copies-and-labels', label: 'Copies and Labels'},
      ],
    },
    {
      type: 'category',
      label: 'Operations',
      items: [
        {type: 'doc', id: 'operations/mac-mini-deployment', label: 'Mac Mini Deployment'},
        {type: 'doc', id: 'operations/backup', label: 'Backup'},
        {type: 'doc', id: 'operations/troubleshooting', label: 'Troubleshooting'},
      ],
    },
  ],
  developerGuide: [
    {
      type: 'category',
      label: 'Technical Details',
      items: [
        {type: 'doc', id: 'technical-details/architecture', label: 'Architecture'},
        {type: 'doc', id: 'technical-details/photo-identification', label: 'Photo Identification'},
        {type: 'doc', id: 'technical-details/testing', label: 'Testing'},
      ],
    },
    {
      type: 'category',
      label: 'Project',
      items: [
        {type: 'doc', id: 'about/roadmap', label: 'Roadmap'},
        {type: 'doc', id: 'about/license', label: 'License'},
      ],
    },
  ],
};

export default sidebars;
