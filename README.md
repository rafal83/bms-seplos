# Intégration Home Assistant HACS - Seplos BMS (Bluetooth / BLE)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/default)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-blue.svg)](https://www.home-assistant.io/)

Intégration personnalisée Home Assistant (compatible **HACS**) pour gérer et surveiller votre batterie équipée d'un **BMS Seplos** en Bluetooth Low Energy (BLE).

Cette intégration remplace et enrichit l'application mobile **BMS (`com.example.bms_flutter` / EN BMS)** en intégrant toutes les données et états de votre batterie directement dans votre domotique Home Assistant.

---

## ✨ Fonctionnalités

- **Découverte automatique Bluetooth** : Home Assistant détecte votre batterie dès qu'elle émet en Bluetooth (noms commençant par `SP*`, `BP*`, `XZHX*`, `CSY*`, `ST*`, `SmartBat*` ou services BLE dédiés).
- **Compatible Seplos V2 et V3** : Prise en charge automatique des protocoles V2 (ASCII) et V3 (Modbus RTU).
- **Support des Proxys Bluetooth ESPHome** : Fonctionne parfaitement même si votre batterie est éloignée du serveur Home Assistant grâce aux proxys Bluetooth.
- **Capteurs complets** :
  - ⚡ **Tension totale** (V)
  - 🔌 **Courant de charge / décharge** (A)
  - 💡 **Puissance** (W) calculée en temps réel
  - 🔋 **Niveau de batterie (SOC %)** et **État de santé (SOH %)**
  - 📦 **Capacité nominale** et **Capacité restante** (Ah)
  - 🔄 **Nombre de cycles** de charge
  - 🌡️ **Température** moyenne, minimale et maximale des cellules, ambiante et MOSFET
  - 📊 **Tensions individuelles de chaque cellule** (Cellule 1 à 16 ou 24)
  - ⚖️ **Écart de tension entre cellules** (*Cell Delta* en mV) pour surveiller l'équilibrage
  - 🏷️ **Numéro de la cellule la plus faible et la plus forte**
- **Capteurs binaires d'état et sécurité** :
  - 🟢 Charge autorisée (MOSFET de charge)
  - 🟢 Décharge autorisée (MOSFET de décharge)
  - ⚖️ Équilibrage actif (*Balancer*)
  - ♨️ Chauffage de batterie actif (*Heater*)
  - ⚠️ Alerte / Problème détecté (avec liste détaillée des alarmes actives en attributs)
- **Bouton d'actualisation instantanée** : pour forcer une lecture immédiate de la télémétrie.

---

## 🚀 Installation

### Méthode 1 : Via HACS (Recommandée)

1. Ouvrez **Home Assistant**.
2. Allez dans **HACS** > **Intégrations**.
3. Cliquez sur le menu en haut à droite (3 points) > **Dépôts personnalisés** (*Custom repositories*).
4. Ajoutez l'URL de votre dépôt Git :
   - **Catégorie** : `Intégration`
5. Cliquez sur **Ajouter**, puis recherchez **Seplos BMS (Bluetooth)** et cliquez sur **Télécharger**.
6. Redémarrez **Home Assistant**.

---

### Méthode 2 : Installation manuelle

1. Téléchargez le dossier `custom_components/seplos_bms`.
2. Copiez le dossier `seplos_bms` dans le répertoire `config/custom_components/` de votre serveur Home Assistant :
   ```text
   config/
   └── custom_components/
       └── seplos_bms/
           ├── __init__.py
           ├── manifest.json
           ├── coordinator.py
           ├── config_flow.py
           ├── const.py
           ├── sensor.py
           ├── binary_sensor.py
           ├── button.py
           ├── strings.json
           └── translations/
               ├── fr.json
               └── en.json
   ```
3. Redémarrez **Home Assistant**.

---

## ⚙️ Configuration

1. Rendez-vous dans **Paramètres** > **Appareils et services** > **Intégrations**.
2. Si votre batterie est à portée ou captée par un proxy Bluetooth, une notification de découverte apparaîtra automatiquement : cliquez sur **Configurer**.
3. Si elle n'apparaît pas automatiquement :
   - Cliquez sur **Ajouter une intégration** en bas à droite.
   - Recherchez **Seplos BMS (Bluetooth)**.
   - Sélectionnez votre BMS dans la liste des appareils Bluetooth détectés ou entrez manuellement son adresse MAC Bluetooth (ex: `C0:D6:3C:XX:XX:XX`).
4. Choisissez le protocole (**Auto** recommandé, ou forcez **Seplos V2** / **Seplos V3** selon votre matériel).
5. Définissez l'intervalle d'actualisation souhaité (par défaut : 30 secondes).

---

## 🛠️ Dépannage et Logs

Pour activer le mode débogage de l'intégration, ajoutez dans votre `configuration.yaml` :

```yaml
logger:
  default: info
  logs:
    custom_components.seplos_bms: debug
    aiobmsble: debug
```

Puis rechargez la configuration des logs ou redémarrez Home Assistant.

