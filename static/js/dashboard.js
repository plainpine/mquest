document.addEventListener('DOMContentLoaded', function() {
  (function() {
    console.log("DOM fully loaded and script executing.");

    // Defensive data acquisition from data attribute
    const dataElement = document.getElementById('conquered-data');
    let student_conquered_list = []; // Default to an empty array
    if (dataElement) {
      const conqueredJSON = dataElement.getAttribute('data-conquered');
      try {
        if (conqueredJSON) {
          student_conquered_list = JSON.parse(conqueredJSON);
        }
      } catch (e) {
        console.error("Error parsing conquered list JSON:", e, conqueredJSON);
      }
    } else {
      console.error('Error: Data element #conquered-data not found.');
    }
    
    let currentMapType = 'europe';

    function highlightMap(mapType) {
        const svgObject = document.querySelector(`#map-${mapType} object`);
        if (!svgObject) return;

        const onSvgLoad = () => {
            const svgDoc = svgObject.contentDocument;
            if (!svgDoc) return;

            svgDoc.querySelectorAll('path, rect').forEach(p => p.classList.remove('conquered'));

            // Ensure student_conquered_list is an array before using forEach
            if (Array.isArray(student_conquered_list)) {
              student_conquered_list.forEach(id => {
                  const element = svgDoc.getElementById(`${mapType}-${id}`);
                  if (element) {
                      element.classList.add('conquered');
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