# Projet pCloud Docker

Ce projet permet de configurer et d'exécuter le client pCloud en utilisant Docker et Docker Compose.

## Prérequis

- Docker
- Docker Compose

## Configuration

Avant de lancer les services, assurez-vous d'avoir configuré les variables d'environnement suivantes :

- `PCLOUD_USERNAME` : votre nom d'utilisateur pCloud
- `PCLOUD_PASSWORD` : votre mot de passe pCloud

Vous pouvez définir ces variables dans un fichier `.env` à la racine du projet :

```env
PCLOUD_USERNAME=votre_nom_utilisateur
PCLOUD_PASSWORD=votre_mot_de_passe
