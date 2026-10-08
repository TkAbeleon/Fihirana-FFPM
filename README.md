# Fihirana-FFPM

Données JSON de chants issus notamment de Fihirana FFPM, Fihirana Fanampiny, Antema et TSANTA.

## MiReDo

Ce dépôt sert également de base documentaire et de données pour **MiReDo**, une application desktop Rust de bibliothèque et de lecture de chants.

La conception complète est dans [docs/miredo/](./docs/miredo/).

### Documentation MiReDo

- [Vue d'ensemble](./docs/miredo/00-vue-ensemble.md)
- [Architecture](./docs/miredo/01-architecture.md)
- [Modèle de données](./docs/miredo/02-modele-donnees.md)
- [Design system](./docs/miredo/03-design-system.md)
- [UX/UI](./docs/miredo/04-ux-ui.md)
- [Pages et navigation](./docs/miredo/05-pages-navigation.md)
- [Lecteurs PDF et texte](./docs/miredo/06-lecteurs.md)
- [I18n et thèmes](./docs/miredo/07-i18n-themes.md)
- [Persistance et recherche](./docs/miredo/08-persistance-recherche.md)
- [Roadmap et qualité](./docs/miredo/09-roadmap-qualite.md)
- [Choix technologiques](./docs/miredo/10-choix-technologiques.md)

### Principes MiReDo

- Rust desktop multiplateforme.
- Un **Song** central avec vue partition et vue texte.
- Bascule PDF ↔ Texte sans perdre le contexte.
- Interface moderne de productivité desktop, sobre et orientée contenu.
- **FR / MG / EN dans un seul fichier** resources/i18n.json.
- **Toutes les couleurs dans un seul fichier** resources/palette.json.
- Pages dédiées **Accueil, Bibliothèque, Favoris, Mes listes, Paramètres, Aide et À propos**.
- Recherche par numéro, titre, auteur et paroles.
- Fonctionnement hors ligne pour les fonctions principales.
