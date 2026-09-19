# MDRS field topology

Hosts and Meshtastic gateway nodes at MDRS.

```mermaid
flowchart LR
    subgraph attic [Hab attic]
        H2[hab2 gw]
        S1[solar1 pc]
        MP[meshpi pizero2]
        H3[hab3 gw]
        DR[drone receiver]
        ADSB[adsb receiver]
        AUDIO[all-in-one audio]

        S1 -- USB --- H2
        MP -- USB --- H3
        S1 -- USB --- DR
        S1 -- USB --- ADSB
        S1 -- USB --- AUDIO
    end
```
