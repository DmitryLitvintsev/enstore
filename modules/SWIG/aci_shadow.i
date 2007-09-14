/************************************************************
 *
 *   $Id$
 *
 * SWIG input file for aci_shadowcmodule
 *
 ************************************************************/

%module aci_shadow


%{
#include "aci.h"
#include "aci_typedefs.h"
%}

/*-------------------------------------------------------------------------*/

#include <sys/types.h>
#include <rpc/rpc.h>    /* for bool_t   */
#include "derrno.h"     /* das errnos   */
#include <netinet/in.h>

%include "typemaps.i"   /* SWIG standard typemaps */
%include "aci_typedefs.h"
%include "aci_typemaps.i"

/*-------------------------------------------------------------------------*/

enum aci_media { ACI_3480 = 1, ACI_OD_THICK, ACI_OD_THIN,
                 ACI_DECDLT, ACI_8MM, ACI_4MM, ACI_D2, ACI_VHS, ACI_3590,
                 ACI_CD, ACI_TRAVAN, ACI_DTF, ACI_BETACAM, ACI_AUDIO_TAPE,
		 /* From version 3.1.2 */
                 ACI_BETACAML, ACI_SONY_AIT, ACI_LTO, ACI_DVCM, ACI_DVCL,
                 ACI_NUMOF_MEDIA, ACI_MEDIA_AUTO=999 };

enum aci_command {ACI_ADD = 1, ACI_MODIFY, ACI_DELETE};
enum aci_drive_status {ACI_DRIVE_DOWN = 1, ACI_DRIVE_UP, 
     /* From version 3.1.2 */
     ACI_DRIVE_FDOWN, ACI_DRIVE_FUP, ACI_DRIVE_EXUP};

/*-------------------------------------------------------------------------*/

#define ACI_COORD_LEN   11      /* should match das.h setting */
#define ACI_VOLSER_LEN  17      /* should match das.h setting */
#define ACI_NAME_LEN    65      /* should match das.h setting */
#define ACI_REQTYPE_LEN 10      /* should match das.h setting */
#define ACI_DRIVE_LEN   10      /* should match das.h setting */
#define ACI_AMU_DRIVE_LEN 3     /* should be das.h setting +1 */
#define ACI_OPTIONS_LEN 3       /* should match das.h setting */
#define ACI_MAX_RANGES  10      /* should match das.h setting */
#define ACI_RANGE_LEN   100     /* should match das.h setting */
#define ACI_POOLNAME_LEN  17    /* should match das.h setting */

#define ACI_MAX_REQ_ENTRIES 15  /* should match das.h setting */
#define ACI_MAX_DRIVE_ENTRIES 15 /* should match das.h setting */
#define ACI_MAX_DRIVE_ENTRIES2 250 /* should match das.h setting */
#define ACI_MAX_DRIVE_ENTRIES4 380 /* should match das.h setting */

#define ACI_MAX_VERSION_LEN 20   /*           including '\0'   */
#define ACI_MAX_QUERY_VOLSRANGE 1000

#define ACI_VOLSER_ATTRIB_MOUNTED   'M'
#define ACI_VOLSER_ATTRIB_EJECTED   'E'
#define ACI_VOLSER_ATTRIB_OCCUPIED  'O'
#define ACI_VOLSER_ATTRIB_UNDEFINED 'U'
/* From version 3.1.2 */
#define ACI_VOLSER_ATTRIB_EMPTY             'Y'
#define ACI_VOLSER_ATTRIB_REVERSSIDEMOUNTED 'R'
#define ACI_VOLSER_ATTRIB_IN_JUKEBOX        'J'
#define ACI_VOLSER_ATTRIB_INITIAL           'I'
#define ACI_VOLSER_ATTRIB_TEMP_HERE         'T'
#define ACI_VOLSER_ATTRIB_TEMP_AWAY         'A'

/*---------- 3.11 -----------------------------*/
#define ACI_MS_OCC     0x01
#define ACI_MS_MKE     0x02
#define ACI_MS_MNT     0x04
#define ACI_MS_EJT     0x08
#define ACI_MS_UNDEF   0x10
#define ACI_MS_EMPTY   ACI_MS_MKE | ACI_MS_EJT
#define ACI_MS_ALL     ACI_MS_OCC|ACI_MS_MNT|ACI_MS_UNDEF|ACI_MS_EMPTY

/*-------------------------------------------------------------------------*/

struct aci_vol_desc {
        char coord[ACI_COORD_LEN];
        char owner;
        char attrib;
        char type;
        char volser[ACI_VOLSER_LEN];
        char vol_owner;
        int use_count;
        int crash_count;
};


struct aci_drive_entry {
    char drive_name[ACI_DRIVE_LEN];
    char amu_drive_name[ACI_AMU_DRIVE_LEN];
    enum aci_drive_status drive_state;
    char type;
    char system_id[ACI_NAME_LEN];
    char clientname[ACI_NAME_LEN];
    char volser[ACI_VOLSER_LEN];
    bool_t cleaning;
    short clean_count;
};

struct aci_ext_drive_entry {
        char                   drive_name[ACI_DRIVE_LEN];
        char                   amu_drive_name[ACI_AMU_DRIVE_LEN];
        enum aci_drive_status  drive_state;
        char                   type;
        char                   system_id[ACI_NAME_LEN];
        char                   clientname[ACI_NAME_LEN];
        char                   volser[ACI_VOLSER_LEN];
        bool_t                 cleaning;
        short                  clean_count;
        int                    mount;
        int                    keep;
};

struct aci_ext_drive_entry4 {
        char                   drive_name[ACI_DRIVE_LEN];
        char                   amu_drive_name[ACI_AMU_DRIVE_LEN];
        enum aci_drive_status  drive_state;
        char                   type;
        char                   system_id[ACI_NAME_LEN];
        char                   clientname[ACI_NAME_LEN];
        char                   volser[ACI_VOLSER_LEN];
        bool_t                 cleaning;
        short                  clean_count;
        int                    mount;
        int                    keep;
        char                   serial_number[ACI_SERIAL_NUMBER_LEN];
};

struct in_addr {
	unsigned int s_addr;
};

struct aci_client_entry {
        char clientname[ACI_NAME_LEN];
        struct in_addr ip_addr;
        bool_t avc;
        bool_t complete_access;
        bool_t dismount;
	char volser_range[ACI_MAX_RANGES][ACI_RANGE_LEN];
        char drive_range [ACI_RANGE_LEN];
};


struct aci_req_entry {
        u_long request_no;
        u_long individ_no;
        char clientname [ACI_NAME_LEN];
        char req_type [ACI_REQTYPE_LEN + 1];
};

struct aci_volserinfo
{
       char            volser [ ACI_VOLSER_LEN ];
       enum aci_media  media_type;
       char            attrib;
};

struct  aci_media_info {
         enum aci_media  eMediaType;
         unsigned long   ulCount;
};

int aci_robhome (char *); 
int aci_robstat (char *, char *); 

int aci_cancel (int request_id);
extern int aci_clientaccess (char *clientname, enum aci_command, char *volser_range,
			     enum aci_media, char *drive_range); 
extern int aci_clientstatus (char *clientname, struct aci_client_entry *client);
extern int aci_dismount (char *, enum aci_media);
extern int aci_driveaccess (char *, char *, enum aci_drive_status);
extern int aci_drivestatus (char *, struct aci_drive_entry *[ACI_MAX_DRIVE_ENTRIES]);
extern int aci_drivestatus2 (char *, struct aci_drive_entry *[ACI_MAX_DRIVE_ENTRIES2]);
extern int aci_drivestatus3 (char *, struct aci_ext_drive_entry *[ACI_MAX_DRIVE_ENTRIES2]);
extern int aci_drivestatus4 (char *, char *, struct aci_ext_drive_entry4 *[ACI_MAX_DRIVE_ENTRIES4], int *);
extern int aci_eject (char *, char *, enum aci_media);
extern int aci_eject_complete( char *, char *, enum aci_media );
extern int aci_force (char *);
extern int aci_foreign (enum aci_command, char *, enum aci_media, char *,short);
extern int aci_init (void);
extern int aci_insert (char *, char *volser_ranges[ACI_MAX_RANGES], enum aci_media *); 
extern int aci_list (char *, struct aci_req_entry *[ACI_MAX_REQ_ENTRIES]);
extern int aci_mount (char *, enum aci_media, char *);
extern int aci_move (char *, enum aci_media, char *);
extern int aci_carry( char *, char *, char *, int *);
extern void aci_perror (char *);
extern int aci_register (char *, char *, enum aci_command,bool_t,bool_t,bool_t);
extern int aci_shutdown (char *);
extern int aci_view (char *, enum aci_media, struct aci_vol_desc *desc);

extern int aci_initialize( void );

extern int aci_qversion( version_string, version_string);
/* We need to name nCount and volserinfo so that the mappings from
   aci_typemaps.i only apply to aci_qvolsrange().  Otherwise, collisions
   occur in the namespace. */
extern int aci_qvolsrange( char *volser, char *, int, char *clientname,
                           int * nCount, struct aci_volserinfo * volserinfo);
extern int aci_partial_inventory( char *, char *);
extern int aci_inventory( void );
extern int aci_scratch_set (char *, enum aci_media , char * );
extern int aci_scratch_get (char *, enum aci_media , char * );
extern int aci_scratch_unset (char *, enum aci_media , char * );
extern int aci_scratch_info (char *,  enum aci_media , long *, long *);

/*   3.11   */
extern int  aci_getcellinfo( char*, enum aci_media, unsigned int,
			     int * nCount,
			     struct aci_media_info * media_info);

/*-------------------------------------------------------------------------*/

extern int d_errno;     /*  global object for error return from aci_ call */


/************ I don't think we need any of these globals.........
extern char *szRetDrive[15]; 
extern  int   iMediaType;
extern  char  szMediaType[];

extern  char  szVolser[];
extern  char  szSourceCoord[];
extern  char  szTargetCoord[];
*********************************************************/


/*-------------------------------------------------------------------------*/
/*  E n d                                                                  */
/*-------------------------------------------------------------------------*/




