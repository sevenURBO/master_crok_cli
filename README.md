# Master Crok - Python Implementation 🃏

![Python](https://img.shields.io/badge/python-3.8%2B-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

An open-source, Command Line Interface (CLI) implementation of the classic **Master Crok** card game. This project aims to digitally recreate the nostalgic gameplay experience, ability systems, and the "Group Victory" mechanic.

## 📋 Features

This implementation handles the core logic of the card game, including:

* **Dynamic Card Database:** Cards are loaded from an external `cards.json` file.
* **Combat System:** Rock-Paper-Scissors style attribute system (**Power**, **Intelligence**, **Reflex**) with tie-breaking mechanics.
* **Ability Engine:** Supports both active (e.g., swapping cards mid-turn) and passive abilities (e.g., attribute buffs based on opponent stats).
* **Advanced Ruleset:**
    * **Blind Fight:** Resolves draws using the top card of the deck.
    * **Group Victory:** Tracks distinct group wins for alternate win conditions.

## 🚀 Installation & Usage

This project runs on standard Python libraries. No external dependencies (`pip install`) are required.

### Prerequisites
* [Python 3.x](https://www.python.org/downloads/) installed on your system.

### Running the Game

1. **Clone the repository:**
   ```bash
   git clone https://github.com/sevenURBO/master-crok-cli.git
   cd master-crok-cli

2.  **Start the application:**
    ```bash
    python main.py
    ```
## 🎮 How to Play

The game runs in the terminal. Follow the on-screen prompts:

1.  **Draw Phase:** You start with 4 cards. A new card is drawn at the start of every battle.
2.  **Attack:** If it is your turn, choose an attribute (1: Power, 2: Intelligence, 3: Reflex) and select a card to play.
3.  **Defend:** The opponent responds. If values are equal, a **Blind Fight** occurs.
4.  **Victory:** Collect won cards. The first player to achieve **6 Group Victories** (different factions) or the player with the most wins when decks are empty takes the game.
