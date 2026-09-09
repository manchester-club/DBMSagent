typedef enum AlterTableType
{
	AT_AddColumn,
	AT_DetachPartition,			/* DETACH PARTITION */
	AT_EnableAlways,			/* ENABLE ALWAYS */
} AlterTableType;
