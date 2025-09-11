document.addEventListener('DOMContentLoaded', function() {
  (function() {
    console.log("DOM fully loaded and script executing.");

    const dataElement = document.getElementById('conquered-data');
    let conquered_quest_data = []; // Default to an empty array
    if (dataElement) {
      const conqueredJSON = dataElement.getAttribute('data-conquered');
      try {
        if (conqueredJSON) {
          conquered_quest_data = JSON.parse(conqueredJSON);
        }
      } catch (e) {
        console.error("Error parsing conquered list JSON:", e, conqueredJSON);
      }
    } else {
      console.error('Error: Data element #conquered-data not found.');
    }
    
    let currentMapType = 'europe';

    function getAttemptTierClass(attempts) {
      if (attempts <= 2) {
        return 'attempt-tier-1';
      } else if (attempts <= 4) {
        return 'attempt-tier-2';
      } else if (attempts <= 6) {
        return 'attempt-tier-3';
      } else {
        return 'attempt-tier-4';
      }
    }

    function highlightMap(mapType) {
        const svgObject = document.querySelector(`#map-${mapType} object`);
        if (!svgObject) return;

        const onSvgLoad = () => {
            const svgDoc = svgObject.contentDocument;
            if (!svgDoc) return;

            // Reset all paths to default state
            svgDoc.querySelectorAll('path, rect').forEach(p => {
              p.classList.remove('conquered', 'attempt-tier-1', 'attempt-tier-2', 'attempt-tier-3', 'attempt-tier-4');
            });

            if (Array.isArray(conquered_quest_data)) {
              // Filter quests to only those that belong on the current map
              const questsForThisMap = conquered_quest_data.filter(item => item.map_type === mapType);

              questsForThisMap.forEach(item => {
                  const element = svgDoc.getElementById(item.quest_id);
                  if (element) {
                      const tierClass = getAttemptTierClass(item.attempts);
                      element.classList.add('conquered');
                      element.classList.add(tierClass);
                  }
              });
            }
        };

        if (svgObject.contentDocument && svgObject.contentDocument.readyState === 'complete') {
            onSvgLoad();
        } else {
            svgObject.addEventListener('load', onSvgLoad);
        }
    }

    function switchMap(type) {
        currentMapType = type;
        document.querySelectorAll('.map').forEach(m => m.classList.remove('active'));
        const newMap = document.getElementById(`map-${type}`);
        if (newMap) {
            newMap.classList.add('active');
        }
        highlightMap(type);
    }

    // Add click listeners to buttons
    const buttons = document.querySelectorAll('.map-selector button');
    buttons.forEach(button => {
        button.addEventListener('click', (event) => {
            const type = event.currentTarget.dataset.mapType;
            if (!type) return;

            document.querySelectorAll('.map-selector button').forEach(btn => {
                btn.classList.remove('active', 'btn-primary');
                btn.classList.add('btn-secondary');
            });
            event.currentTarget.classList.add('active', 'btn-primary');
            event.currentTarget.classList.remove('btn-secondary');
            
            switchMap(type);
        });
    });

    // Initial Load
    document.querySelectorAll('.map').forEach(m => m.classList.remove('active'));
    const initialMap = document.getElementById(`map-${currentMapType}`);
    if (initialMap) {
        initialMap.classList.add('active');
    }
    highlightMap(currentMapType);

    // Add listeners for subsequent loads to handle caching
    document.querySelectorAll('.map object').forEach(obj => {
        obj.addEventListener('load', () => {
            const mapId = obj.parentElement.id.split('-')[1];
            highlightMap(mapId);
        });
    });
  })();
});